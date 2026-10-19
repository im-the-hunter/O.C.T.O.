"""
Capa de acceso a Pinecone — Fase 5 (PARTE A).

Único punto de contacto del backend con la base de datos vectorial.
Usa el cliente oficial `pinecone` (>= 4.x, API "inference / serverless") y
expone exactamente cuatro responsabilidades:

- Conexión perezosa mediante variables de entorno (PINECONE_API_KEY, ...).
- initialize_index():  crea el índice "jarvis-repo" si no existe.
- upsert_chunks():     sube vectores (embeddings + metadata) en batches.
- search_similar():    búsqueda por similitud coseno con top_k.

Todos los errores de conexión/API se capturan y se elevan como
`PineconeServiceError` con mensajes claros, de modo que los servicios de
alto nivel (rag_service, ingest_repo) puedan degradar elegantemente.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger("jarvis.pinecone")


# ---------------------------------------------------------------------------
# Errores y tipos de dominio
# ---------------------------------------------------------------------------
class PineconeServiceError(RuntimeError):
    """Error de conexión/configuración/operación contra Pinecone."""


@dataclass
class VectorChunk:
    """Representación neutralizada de un chunk listo para subir."""

    id: str
    values: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Match:
    """Resultado de una búsqueda similar."""

    id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    values: Optional[list[float]] = None


# ---------------------------------------------------------------------------
# Cliente envoltorio
# ---------------------------------------------------------------------------
class PineconeClient:
    """Envoltorio asíncrono y tolerante a fallos sobre el cliente oficial."""

    def __init__(self) -> None:
        self._api_key = settings.pinecone_api_key
        self._index_name = settings.pinecone_index_name
        self._dimensions = settings.embedding_dimensions
        self._spec_cloud = "aws"
        self._spec_region = "us-east-1"

        self._pc: Any = None            # pinecone.Pinecone
        self._index: Any = None         # pinecone.Index
        self._initialized = False

    # -- helpers internos ---------------------------------------------------
    def _ensure_sync_available(self) -> None:
        """La SDK de Pinecone es síncrona; prohibimos llamarla desde el loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # No hay loop corriendo: es seguro ejecutar en línea.
        raise PineconeServiceError(
            "PineconeClient es blocking: usa las variantes '..._async' dentro "
            "de un event loop (asyncio.to_thread)."
        )

    def _get_pinecone(self) -> Any:
        """Conexión perezosa al servicio Pinecone."""
        if self._pc is not None:
            return self._pc

        if not self._api_key:
            raise PineconeServiceError(
                "PINECONE_API_KEY no está configurada. Añádela a tu .env "
                "(ver .env.example)."
            )
        try:
            from pinecone import Pinecone  # import diferido: dependencia opcional
        except ImportError as exc:  # pragma: no cover
            raise PineconeServiceError(
                "Librería 'pinecone' no instalada. Ejecuta: "
                "pip install 'pinecone-client>=4.0'"
            ) from exc

        try:
            self._pc = Pinecone(api_key=self._api_key)
            logger.info("Conexión Pinecone establecida (índice: %s)", self._index_name)
        except Exception as exc:  # noqa: BLE001
            raise PineconeServiceError(f"Fallo al conectar con Pinecone: {exc}") from exc
        return self._pc

    def _attach_index(self) -> Any:
        """Abre el índice existente y cachea la referencia."""
        if self._index is not None:
            return self._index
        pc = self._get_pinecone()
        try:
            self._index = pc.Index(self._index_name)
        except Exception as exc:  # noqa: BLE001
            raise PineconeServiceError(
                f"No se pudo abrir el índice '{self._index_name}': {exc}. "
                "¿Existe todavía? Ejecuta initialize_index()."
            ) from exc
        return self._index

    # -- API pública (síncrona) ---------------------------------------------
    def initialize_index(self) -> dict[str, Any]:
        """Crea el índice 'jarvis-repo' (1536 dims, cosine) si no existe.

        Idempotente: si ya existe, simplemente lo abre. Espera a que esté
        Ready antes de retornar.
        """
        self._ensure_sync_available()
        pc = self._get_pinecone()

        try:
            if pc.exists(self._index_name):
                logger.info("Índice '%s' ya existe.", self._index_name)
            else:
                logger.info(
                    "Creando índice '%s' (dims=%d, metric=cosine, %s/%s)...",
                    self._index_name, self._dimensions, self._spec_cloud, self._spec_region,
                )
                pc.create_index(
                    name=self._index_name,
                    dimension=self._dimensions,
                    metric="cosine",
                    spec={
                        "serverless": {
                            "cloud": self._spec_cloud,
                            "region": self._spec_region,
                        }
                    },
                )
                # Esperar a que esté listo (hasta ~90 s)
                for _ in range(30):
                    desc = pc.describe_index(self._index_name)
                    if getattr(desc, "status", {}).get("ready") or desc.get("status", {}).get("ready"):
                        break
                    import time as _t

                    _t.sleep(3)
        except PineconeServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PineconeServiceError(f"Error al inicializar el índice: {exc}") from exc

        index = self._attach_index()
        self._initialized = True
        try:
            stats = index.describe_index_stats()
            vector_count = stats.get("total_vector_count", 0)
        except Exception:  # noqa: BLE001
            vector_count = -1  # no crítico
        return {
            "index": self._index_name,
            "dimension": self._dimensions,
            "metric": "cosine",
            "created_or_reused": True,
            "vector_count": vector_count,
        }

    def upsert_chunks(self, chunks: list[VectorChunk], batch_size: int = 100) -> int:
        """Sube vectores (id + embedding + metadata) en batches.

        Retorna el número total de vectores upsertados. La metadata debe ser
        serializable por Pinecone (str/int/float/bool/list[str]); los valores
        de otros tipos se convierten a str por seguridad.
        """
        self._ensure_sync_available()
        if not chunks:
            return 0

        index = self._attach_index()
        total = 0
        try:
            for start in range(0, len(chunks), batch_size):
                batch = chunks[start : start + batch_size]
                vectors = [
                    {"id": c.id, "values": c.values, "metadata": _sanitize_metadata(c.metadata)}
                    for c in batch
                ]
                index.upsert(vectors=vectors)
                total += len(vectors)
                logger.debug("Upsert batch %d-%d (%d vectores)", start, start + len(batch), len(batch))
        except Exception as exc:  # noqa: BLE001
            raise PineconeServiceError(f"Error al hacer upsert en Pinecone: {exc}") from exc
        logger.info("Upsert completado: %d vectores en '%s'", total, self._index_name)
        return total

    def search_similar(
        self,
        query_vector: list[float],
        top_k: int = 5,
        namespace: str = "",
        filters: Optional[dict[str, Any]] = None,
        include_metadata: bool = True,
        include_values: bool = False,
    ) -> list[Match]:
        """Búsqueda por similitud coseno sobre un vector de consulta ya generado.

        Args:
            query_vector: embedding de la query (dimensión == settings.embedding_dimensions).
            top_k: número máximo de resultados.
            namespace: namespace de Pinecone ("" = por defecto).
            filters: filtro por metadata, ej. {"language": "typescript"}.
            include_metadata/include_values: controlan el payload de la respuesta.

        Returns:
            Lista de `Match` ordenada por score descendente.
        """
        self._ensure_sync_available()
        if not query_vector:
            raise PineconeServiceError("query_vector vacío: genera el embedding primero.")
        if len(query_vector) != self._dimensions:
            raise PineconeServiceError(
                f"Dimensión del vector ({len(query_vector)}) no coincide con la del "
                f"índice ({self._dimensions})."
            )

        index = self._attach_index()
        try:
            resp = index.query(
                vector=query_vector,
                top_k=top_k,
                namespace=namespace,
                filter=filters or None,
                include_metadata=include_metadata,
                include_values=include_values,
            )
        except Exception as exc:  # noqa: BLE001
            raise PineconeServiceError(f"Error en búsqueda vectorial: {exc}") from exc

        matches: list[Match] = []
        for m in resp.get("matches", []) or []:
            matches.append(
                Match(
                    id=str(m.get("id", "")),
                    score=float(m.get("score", 0.0)),
                    metadata=m.get("metadata", {}) or {},
                    values=m.get("values"),
                )
            )
        return matches

    def delete_by_ids(self, ids: list[str], namespace: str = "") -> None:
        """Elimina vectores por lista de IDs (para ingesta incremental)."""
        self._ensure_sync_available()
        if not ids:
            return
        index = self._attach_index()
        try:
            for start in range(0, len(ids), 1000):
                index.delete(ids=ids[start : start + 1000], namespace=namespace)
        except Exception as exc:  # noqa: BLE001
            raise PineconeServiceError(f"Error al eliminar vectores: {exc}") from exc

    def delete_by_filter(self, filters: dict[str, Any], namespace: str = "") -> None:
        """Elimina vectores que coinciden con un filtro de metadata."""
        self._ensure_sync_available()
        if not filters:
            raise PineconeServiceError("delete_by_filter requiere filtros no vacíos.")
        index = self._attach_index()
        try:
            index.delete(filter=filters, namespace=namespace)
        except Exception as exc:  # noqa: BLE001
            raise PineconeServiceError(f"Error al eliminar por filtro: {exc}") from exc

    def get_namespace_stats(self) -> dict[str, Any]:
        """Estadísticas básicas del índice (conteo de vectores, namespaces)."""
        self._ensure_sync_available()
        index = self._attach_index()
        try:
            stats = index.describe_index_stats()
            return dict(stats) if not isinstance(stats, dict) else stats
        except Exception as exc:  # noqa: BLE001
            raise PineconeServiceError(f"Error al leer estadísticas: {exc}") from exc

    # -- API pública (asíncrona: delega al thread pool) ----------------------
    async def initialize_index_async(self) -> dict[str, Any]:
        return await asyncio.to_thread(self.initialize_index)

    async def upsert_chunks_async(self, chunks: list[VectorChunk], batch_size: int = 100) -> int:
        return await asyncio.to_thread(self.upsert_chunks, chunks, batch_size)

    async def search_similar_async(
        self,
        query_vector: list[float],
        top_k: int = 5,
        namespace: str = "",
        filters: Optional[dict[str, Any]] = None,
        include_metadata: bool = True,
        include_values: bool = False,
    ) -> list[Match]:
        return await asyncio.to_thread(
            self.search_similar,
            query_vector,
            top_k,
            namespace,
            filters,
            include_metadata,
            include_values,
        )


# ---------------------------------------------------------------------------
# Normalización de metadata (Pinecone solo acepta tipos primitivos)
# ---------------------------------------------------------------------------
def _sanitize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, bool):
            clean[k] = v
        elif isinstance(v, (int, float)):
            clean[k] = v
        elif isinstance(v, str):
            clean[k] = v
        elif isinstance(v, list) and all(isinstance(x, str) for x in v):
            clean[k] = v
        elif v is not None:
            clean[k] = str(v)
    return clean


# ---------------------------------------------------------------------------
# Singleton perezoso compartido por el resto del backend
# ---------------------------------------------------------------------------
_client: Optional[PineconeClient] = None


def get_pinecone_client() -> PineconeClient:
    global _client
    if _client is None:
        _client = PineconeClient()
    return _client
