"""
Endpoints RAG (Fase 5) — expuestos bajo el prefijo /api/rag.

  POST /api/rag/ingest   -> ingesta del repositorio en Pinecone (incremental o forzada)
  POST /api/rag/query    -> pregunta con contexto del repo (retrieve + GPT-4o)
  GET  /api/rag/status   -> estado del índice vectorial + caché de respuestas

Manejo de errores con HTTPException:
  * 400 -> parámetros inválidos
  * 401 -> credenciales rechazadas por OpenAI/Pinecone
  * 404 -> archivo no encontrado (ingesta unitaria)
  * 503 -> servicio dependiente no configurado o caído (Pinecone/OpenAI/caché)

Todo queda documentado automáticamente en Swagger (/docs).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.cache_service import cache_service
from app.services.rag_service import rag_service

logger = logging.getLogger("jarvis.routers.rag")

router = APIRouter()


# ---------------------------------------------------------------------------
# Modelos de petición/respuesta (Swagger-friendly)
# ---------------------------------------------------------------------------
class IngestRequest(BaseModel):
    force: bool = Field(False, description="Si es true, re-procesa todo desde cero")
    file_path: Optional[str] = Field(
        None,
        description="Ruta concreta para ingesta unitaria (opcional; "
                    "si se omite, se ingiere el snapshot completo del repo)",
    )
    max_files: int = Field(200, ge=1, le=2000, description="Tope de archivos a sincronizar")
    background: bool = Field(
        True,
        description="true -> se dispara en segundo plano (polling vía /status); "
                    "false -> espera a terminar y devuelve las estadísticas",
    )


class IngestResponse(BaseModel):
    accepted: bool
    mode: str = Field(..., description="'full' | 'single-file'")
    status: str = Field(..., description="'running' si es background, resultado si es sync")
    message: str


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Pregunta para JARVIS")
    use_context: bool = Field(True, description="Falso = responde solo el LLM (sin RAG)")
    top_k: int = Field(5, ge=1, le=20, description="Chunks recuperados del repo")
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Historial previo [{role: 'user'|'assistant', content: '...'}]",
    )


class Source(BaseModel):
    file: str
    chunk_index: int = 0
    relevance_score: float


class QueryResponse(BaseModel):
    response: str
    sources: list[Source]
    tokens_used: int
    used_repo_context: bool
    cached: bool


class IndexStatus(BaseModel):
    name: str
    ready: bool
    total_vector_count: Optional[int] = None
    dimension: Optional[int] = None
    metric: Optional[str] = None
    error: Optional[str] = None


class LastIngest(BaseModel):
    status: str
    stats: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class RAGStatusResponse(BaseModel):
    pinecone: IndexStatus
    answer_cache: dict[str, Any]
    last_ingest: LastIngest
    config: dict[str, Any]


# ---------------------------------------------------------------------------
# Utilidades comunes
# ---------------------------------------------------------------------------
def _map_rag_error(exc: Exception, context: str) -> HTTPException:
    """Traduce excepciones del servicio a errores HTTP semánticos."""
    msg = str(exc)
    lowered = msg.lower()
    logger.exception("%s falló: %s", context, msg)

    if isinstance(exc, RuntimeError) and "no está configurada" in lowered:
        return HTTPException(status_code=503, detail=f"Configuración incompleta: {msg}")
    if "unauthorized" in lowered or "invalid api key" in lowered or "401" in lowered:
        return HTTPException(
            status_code=401,
            detail="Credenciales rechazadas por OpenAI/Pinecone. Revisa OPENAI_API_KEY "
                   "y PINECONE_API_KEY.",
        )
    if "not found" in lowered or "no such index" in lowered:
        return HTTPException(status_code=404, detail=f"{context}: {msg}")
    return HTTPException(
        status_code=503,
        detail=f"Servicio RAG temporalmente no disponible ({context}): {msg}. "
               "Reintenta en unos segundos.",
    )


# ---------------------------------------------------------------------------
# POST /ingest
# ---------------------------------------------------------------------------
@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=202,
    summary="Ingiera el repositorio en la base vectorial (Pinecone)",
    description=(
        "Procesa los archivos cacheados del repo: chunking (~500 tokens, overlap 50), "
        "embeddings OpenAI en batches de 100 y upsert al índice `jarvis-repo`. "
        "Es **incremental**: omite archivos cuyo `commit_sha` no cambió, reprocesa los "
        "modificados y elimina chunks de archivos borrados. Con `force=true` re-procesa "
        "todo. También acepta `file_path` para vectorizar un único archivo."
    ),
)
async def ingest(payload: IngestRequest, background_tasks: BackgroundTasks) -> IngestResponse:
    # --- Modo archivo único -------------------------------------------------
    if payload.file_path:
        snapshot = cache_service.get_snapshot()
        if not snapshot:
            raise HTTPException(
                status_code=503,
                detail="No hay snapshot del repositorio en caché. Ejecuta antes "
                       "POST /api/github/sync.",
            )
        files = snapshot.get("files", {})
        data = files.get(payload.file_path)
        if data is None:
            raise HTTPException(
                status_code=404,
                detail=f"Archivo '{payload.file_path}' no existe en el repositorio "
                       f"cacheado ({len(files)} archivos disponibles).",
            )
        try:
            result = await rag_service.ingest_single_file(
                payload.file_path,
                data.get("content", ""),
                sha=data.get("sha", ""),
                last_modified=data.get("last_modified", ""),
            )
            return IngestResponse(
                accepted=True,
                mode="single-file",
                status="done",
                message=f"Ingesta de {payload.file_path} completada: "
                        f"{result.get('chunks_upserted', 0)} chunks subidos.",
            )
        except Exception as exc:  # noqa: BLE001
            raise _map_rag_error(exc, "Ingesta de archivo") from exc

    # --- Modo snapshot completo ----------------------------------------------
    snapshot = cache_service.get_snapshot()
    if not snapshot:
        raise HTTPException(
            status_code=503,
            detail="La caché del repositorio está vacía. Sincroniza primero con "
                   "POST /api/github/sync y luego dispara la ingesta.",
        )

    if payload.background:
        if rag_service.last_ingest.get("status") == "running":
            raise HTTPException(
                status_code=400,
                detail="Ya hay una ingesta en curso. Consulta GET /api/rag/status "
                       "para seguir su progreso.",
            )

        async def _run() -> None:
            try:
                await rag_service.ingest_from_snapshot(snapshot, force=payload.force)
            except Exception as exc:  # noqa: BLE001
                logger.error("Ingesta en background falló: %s", exc)
                rag_service.last_ingest = {
                    "status": "failed", "stats": {}, "errors": [str(exc)][:20],
                }

        background_tasks.add_task(lambda: asyncio.create_task(_run()))
        return IngestResponse(
            accepted=True,
            mode="full",
            status="running",
            message=(
                f"Ingesta {'forzada' if payload.force else 'incremental'} iniciada en "
                "segundo plano. Progreso: GET /api/rag/status -> `last_ingest`."
            ),
        )

    try:
        result = await rag_service.ingest_from_snapshot(snapshot, force=payload.force)
        return IngestResponse(
            accepted=True,
            mode="full",
            status=result.get("status", "done"),
            message=f"Ingesta terminada: {result.get('stats', {})}",
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_rag_error(exc, "Ingesta completa") from exc


# ---------------------------------------------------------------------------
# POST /query
# ---------------------------------------------------------------------------
@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Pregunta a JARVIS sobre el repositorio (pipeline RAG completo)",
    description=(
        "Genera el embedding de la pregunta, recupera los `top_k` chunks más similares "
        "(umbral de similitud + hybrid BM25 + re-ranking), construye el contexto y pide "
        "una respuesta a GPT-4o que cita los archivos fuente. Las preguntas idénticas se "
        "sirven desde caché (TTL 1 hora)."
    ),
)
async def query(payload: QueryRequest) -> QueryResponse:
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="La consulta no puede estar vacía.")

    history = payload.conversation_history
    for h in history:
        if h.get("role") not in ("user", "assistant", "system") or "content" not in h:
            raise HTTPException(
                status_code=400,
                detail="conversation_history debe contener objetos "
                       "{role: user|assistant|system, content: string}.",
            )

    try:
        result = await rag_service.answer_question(
            query=payload.query,
            use_repo_context=payload.use_context,
            conversation_history=history,
        )
        return QueryResponse(
            response=result["response"],
            sources=[Source(**s) for s in result.get("sources", [])],
            tokens_used=int(result.get("tokens_used", 0)),
            used_repo_context=bool(result.get("used_repo_context", payload.use_context)),
            cached=bool(result.get("cached", False)),
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _map_rag_error(exc, "Consulta RAG") from exc


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------
@router.get(
    "/status",
    response_model=RAGStatusResponse,
    summary="Estado del índice vectorial y del sistema RAG",
    description=(
        "Devuelve la preparación del índice Pinecone (`jarvis-repo`), número total de "
        "vectores, métricas de la caché de respuestas y el resultado/progreso de la "
        "última ingesta (útil para polling tras POST /api/rag/ingest)."
    ),
)
async def status(
    detailed: bool = Query(False, description="Incluye configuración efectiva del pipeline"),
) -> RAGStatusResponse:
    try:
        idx_stats = await asyncio.to_thread(rag_service.index_stats)
    except Exception as exc:  # noqa: BLE001
        raise _map_rag_error(exc, "Estado del índice") from exc

    last = rag_service.last_ingest or {"status": "never", "stats": {}, "errors": []}
    config: dict[str, Any] = {}
    if detailed:
        config = {
            "embedding_model": settings.openai_embedding_model,
            "chat_model": settings.openai_model,
            "chunk_tokens": settings.rag_chunk_tokens,
            "chunk_overlap_tokens": settings.rag_chunk_overlap_tokens,
            "min_score": settings.rag_min_score,
            "top_k_default": settings.rag_top_k_default,
            "answer_cache_ttl_seconds": settings.rag_answer_cache_ttl,
            "rerank_enabled": bool(settings.cohere_api_key),
        }

    return RAGStatusResponse(
        pinecone=IndexStatus(**idx_stats),
        answer_cache=rag_service.cache_stats(),
        last_ingest=LastIngest(**last),
        config=config,
    )
