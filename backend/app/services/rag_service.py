"""
Servicio RAG (Retrieval-Augmented Generation) — Fase 5.

Responsabilidades:
- Embeddings OpenAI (text-embedding-3-small, 1536 dims) en batches de 100.
- Gestión del índice Pinecone "jarvis-repo" (creación si no existe, métrica cosine).
- Ingesta INCREMENTAL desde el snapshot de caché de GitHub (Fase 4):
    * archivo sin cambios (mismo sha)      -> se omite
    * archivo modificado (nuevo sha)       -> delete old chunks + upsert nuevos
    * archivo eliminado                    -> delete by file_path filter
- Búsqueda semántica con umbral de similitud, re-ranking (Cohere opcional o
  heurístico), hybrid search vectorial + BM25 sobre los candidatos recuperados
  y filtrado por metadata (language / folder).
- Construcción de contexto formateado y respuesta via GPT-4o con citas.
- Caché de respuestas idénticas (TTL 1 hora).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import time
from collections import Counter
from typing import Any, Optional

import httpx
from openai import AsyncOpenAI

from app.core.config import settings
from app.services.chunking_service import chunk_file

logger = logging.getLogger("jarvis.rag")


# ---------------------------------------------------------------------------
# Utilidades de normalización para pinecone (solo str/int/float/bool/list[str])
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


def chunk_id(file_path: str, index: int) -> str:
    """ID determinista por (ruta, índice de chunk) — clave de idempotencia."""
    digest = hashlib.sha1(f"{file_path}:{index}".encode()).hexdigest()
    safe_path = re.sub(r"[^A-Za-z0-9_-]", "_", file_path)[:80]
    return f"{safe_path}#{digest[:16]}"


# ---------------------------------------------------------------------------
# BM25 ligero (híbrido sobre los candidatos ya recuperados vectorialmente)
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9_]{2,}")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Scorer:
    """BM25 puro en Python (sin dependencias) para re-puntuar candidatos."""

    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.doc_tokens = [_tokenize(d) for d in documents]
        self.doc_lens = [len(t) for t in self.doc_tokens]
        self.avg_len = (sum(self.doc_lens) / len(self.doc_lens)) or 1.0
        self.df: Counter[str] = Counter()
        for tokens in self.doc_tokens:
            self.df.update(set(tokens))
        self.n = max(1, len(documents))

    def score(self, query: str) -> list[float]:
        q_terms = set(_tokenize(query))
        scores: list[float] = []
        for tokens, dl in zip(self.doc_tokens, self.doc_lens):
            tf = Counter(tokens)
            s = 0.0
            for term in q_terms:
                if term not in tf:
                    continue
                idf = math.log(1 + (self.n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                freq = tf[term]
                denom = freq + self.k1 * (1 - self.b + self.b * dl / self.avg_len)
                s += idf * freq * (self.k1 + 1) / denom
            scores.append(s)
        return scores


# ---------------------------------------------------------------------------
# Caché de respuestas (memoria, TTL configurable — default 1h)
# ---------------------------------------------------------------------------
class AnswerCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, dict[str, Any]]] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(query: str) -> str:
        return hashlib.sha256(query.strip().lower().encode()).hexdigest()

    def get(self, query: str) -> Optional[dict[str, Any]]:
        entry = self._store.get(self._key(query))
        if not entry:
            self.misses += 1
            return None
        ts, value = entry
        if time.time() - ts > self.ttl:
            del self._store[self._key(query)]
            self.misses += 1
            return None
        self.hits += 1
        return {**value, "cached": True}

    def set(self, query: str, value: dict[str, Any]) -> None:
        self._store[self._key(query)] = (time.time(), value)
        # Poda simple para no crecer indefinidamente
        if len(self._store) > 500:
            now = time.time()
            self._store = {k: v for k, v in self._store.items() if now - v[0] < self.ttl}

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "entries": len(self._store),
            "ttl_seconds": self.ttl,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(self.hits / total * 100, 1) if total else None,
        }


PROMPT_TEMPLATE = """Eres JARVIS, un asistente de IA experto en desarrollo de software.
Tienes acceso al código del repositorio del usuario.

CONTEXTO DEL REPOSITORIO:
{context}

PREGUNTA DEL USUARIO:
{query}

INSTRUCCIONES:
- Responde basándote en el contexto del repositorio si es relevante
- Si la pregunta es sobre el código, cita los archivos específicos
- Si no hay información relevante en el contexto, usa tu conocimiento general
- Sé conciso pero completo
- Usa formato markdown para código y listas
"""


class RAGService:
    """Fachada asíncrona de todo el pipeline RAG."""

    def __init__(self) -> None:
        self._openai_client: AsyncOpenAI | None = None
        self._pc = None
        self._index = None
        self.answer_cache = AnswerCache(settings.rag_answer_cache_ttl)
        # Estado observable de la última/desencadenada ingesta (polling API)
        self.last_ingest: dict[str, Any] = {"status": "never", "stats": {}, "errors": []}
        self._ingest_lock = asyncio.Lock()

    # -- Clientes perezosos ---------------------------------------------------
    @property
    def _openai(self) -> AsyncOpenAI:
        if self._openai_client is None:
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY no está configurada.")
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    @property
    def pinecone(self):
        if self._pc is None:
            if not settings.pinecone_api_key:
                raise RuntimeError("PINECONE_API_KEY no está configurada.")
            from pinecone import Pinecone

            self._pc = Pinecone(api_key=settings.pinecone_api_key)
        return self._pc

    @property
    def index(self):
        """Conecta (o crea) el índice jarvis-repo — 1536 dims, métrica cosine."""
        if self._index is None:
            pc = self.pinecone
            name = settings.pinecone_index_name
            if not pc.has_index(name):
                logger.info("Índice '%s' no existe: creándolo (%d dims, cosine)...",
                            name, settings.embedding_dimensions)
                pc.create_index(
                    name=name,
                    dimension=settings.embedding_dimensions,
                    metric="cosine",
                    spec={"serverless": {
                        "cloud": "aws",
                        "region": settings.pinecone_environment or "us-east-1",
                    }},
                )
                for _ in range(60):  # wait until ready (máx ~2 min)
                    try:
                        if pc.describe_index(name).status.ready:
                            break
                    except Exception:  # noqa: BLE001
                        pass
                    time.sleep(2)
            self._index = pc.Index(name)
        return self._index

    # -- Embeddings ------------------------------------------------------------
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embeddings en batches de 100 (límite recomendado de la API)."""
        vectors: list[list[float]] = []
        for i in range(0, len(texts), 100):
            batch = texts[i : i + 100]
            resp = await self._openai.embeddings.create(
                model=settings.openai_embedding_model, input=batch
            )
            vectors.extend(item.embedding for item in sorted(resp.data, key=lambda d: d.index))
        return vectors

    # -- Ingesta incremental -----------------------------------------------------
    async def ingest_from_snapshot(
        self,
        snapshot: dict[str, Any],
        force: bool = False,
        progress_cb: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Vectoriza el snapshot de caché de GitHub de forma incremental.

        snapshot: estructura de cache_service (repo_tree + files{path:{content,sha}}).
        Compara el sha de cada archivo con el `commit_sha` almacenado en Pinecone;
        solo reprocesa lo que cambió, elimina lo que desapareció del repo.
        """
        async with self._ingest_lock:
            files: dict[str, dict[str, Any]] = snapshot.get("files", {})
            stats = {
                "total_files": len(files), "skipped": 0, "updated": 0, "added": 0,
                "deleted": 0, "chunks_upserted": 0, "chunks_deleted": 0,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            errors: list[str] = []
            self.last_ingest = {"status": "running", "stats": stats, "errors": errors}

            existing = await self._fetch_existing_shas(force)
            repo_commit = (snapshot.get("repo_tree") or {}).get("commit_sha", "")

            paths = sorted(files.keys())
            for n, path in enumerate(paths, 1):
                data = files[path] or {}
                content, sha = data.get("content", ""), data.get("sha", "")
                if progress_cb:
                    progress_cb({"phase": "chunking", "current": n,
                                 "total": len(paths), "file": path})
                # Incremental: mismo sha -> omitir
                if not force and path in existing and existing[path] == sha and sha:
                    stats["skipped"] += 1
                    continue
                try:
                    chunks = chunk_file(
                        path, content,
                        chunk_tokens=settings.rag_chunk_tokens,
                        overlap_tokens=settings.rag_chunk_overlap_tokens,
                    )
                    if not chunks:
                        stats["skipped"] += 1
                        continue

                    if path in existing:  # modificado: limpiar viejos primero
                        await self._delete_file_chunks(path)
                        stats["updated"] += 1
                    else:
                        stats["added"] += 1

                    docs = [{
                        "id": chunk_id(path, c.index),
                        "content": c.text,
                        "metadata": {
                            "file_path": path,
                            "chunk_index": c.index,
                            "total_chunks": c.total,
                            "language": c.metadata.get("language", "text"),
                            "folder": path.rsplit("/", 1)[0] if "/" in path else "",
                            "last_modified": data.get("last_modified", ""),
                            "commit_sha": sha or repo_commit,
                            "repo": snapshot.get("repo", settings.repo_full_name),
                        },
                    } for c in chunks]

                    stats["chunks_upserted"] += await self.upsert_documents(docs)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Error ingiriendo %s", path)
                    errors.append(f"{path}: {exc}")

            # Eliminados del repo: en Pinecone pero ya no en el snapshot
            for path in set(existing) - set(paths):
                try:
                    await self._delete_file_chunks(path)
                    stats["deleted"] += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"delete {path}: {exc}")

            stats["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self.last_ingest = {
                "status": "done" if not errors else "done_with_errors",
                "stats": stats, "errors": errors[:20],
            }
            logger.info("Ingesta completada: %s", stats)
            return self.last_ingest

    async def _fetch_existing_shas(self, force: bool) -> dict[str, str]:
        """file_path -> commit_sha actualmente vectorizado (list + fetch muestreado)."""
        if force:
            return {}
        known: dict[str, str] = {}
        try:
            idx = self.index
            cursor: Optional[str] = None
            for _page in range(50):  # tope de seguridad: 50 páginas x 1000 ids
                kwargs: dict[str, Any] = {"limit": 1000}
                if cursor:
                    kwargs["pagination_token"] = cursor
                resp = idx.list(**kwargs)
                for vec in getattr(resp, "vectors", None) or []:
                    vid = getattr(vec, "id", None) or (vid := "")
                    if vid:
                        known.setdefault(str(vid).split("#", 1)[0], "")
                pagination = getattr(resp, "pagination", None)
                cursor = getattr(pagination, "next_cursor", None) if pagination else None
                if not cursor:
                    break
        except Exception as exc:  # noqa: BLE001 — si falla, modo completo (seguro)
            logger.warning("No se pudo listar el estado previo de Pinecone (%s); ingesta completa.", exc)
            return {}

        # Para conocer el sha real hacemos fetch del chunk #0 de cada archivo (acotado)
        if known:
            try:
                sample = list(known)[:300]
                fetched = self.index.fetch(ids=[chunk_id(p, 0) for p in sample])
                vectors = fetched.get("vectors", {}) if isinstance(fetched, dict) else {}
                for vid, vals in vectors.items():
                    path = str(vid).split("#", 1)[0]
                    if path in known:
                        known[path] = (vals.get("metadata") or {}).get("commit_sha", "")
            except Exception as exc:  # noqa: BLE001
                logger.debug("Fetch parcial de shas existente: %s", exc)
        return known

    async def _delete_file_chunks(self, file_path: str) -> None:
        """Elimina todos los chunks de un archivo por filtro de metadata."""
        self.index.delete(filter={"file_path": file_path})

    async def upsert_documents(self, docs: list[dict]) -> int:
        """Genera embeddings y sube vectores por lotes de 100."""
        if not docs:
            return 0
        vectors = await self.embed([d["content"] for d in docs])
        payload = [
            {
                "id": d["id"],
                "values": v,
                "metadata": {
                    **_sanitize_metadata(d.get("metadata", {})),
                    "text": d["content"][:60_000],  # texto original p/ mostrarlo después
                },
            }
            for d, v in zip(docs, vectors)
        ]
        total = 0
        for i in range(0, len(payload), 100):
            batch = payload[i : i + 100]
            self.index.upsert(vectors=batch)
            total += len(batch)
        return total

    # -- Búsqueda ----------------------------------------------------------------
    async def search_repository(
        self,
        query: str,
        top_k: int = 5,
        *,
        min_score: Optional[float] = None,
        language: Optional[str] = None,
        folder_prefix: Optional[str] = None,
        hybrid: bool = True,
    ) -> list[dict[str, Any]]:
        """Búsqueda semántica + hybrid (BM25) + re-ranking + filtros de metadata.

        Retorna chunks con metadata y score, filtrados por umbral (>0.7 default)
        para evitar resultados irrelevantes.
        """
        threshold = settings.rag_min_score if min_score is None else min_score
        filters: dict[str, Any] = {}
        if language:
            filters["language"] = language
        if folder_prefix:
            filters["folder"] = {"$starts_with": folder_prefix}

        query_vector = (await self.embed([query]))[0]
        fetch_k = max(top_k * 4, 20)  # over-fetch para re-ranking/hybrid
        results = self.index.query(
            vector=query_vector, top_k=fetch_k, include_metadata=True,
            filter=filters or None,
        )
        matches = [
            {
                "id": m["id"],
                "score": float(m["score"]),
                "content": (m.get("metadata") or {}).get("text", ""),
                "file_path": (m.get("metadata") or {}).get(
                    "file_path", str(m["id"]).split("#")[0]
                ),
                "metadata": m.get("metadata") or {},
            }
            for m in results.get("matches", [])
        ]
        if not matches:
            return []

        # Hybrid: combinación de coseno + BM25 normalizado sobre los candidatos
        if hybrid:
            bm25 = BM25Scorer([m["content"] for m in matches]).score(query)
            max_bm = max(bm25) or 1.0
            for m, b in zip(matches, bm25):
                m["bm25_score"] = round(b, 3)
                m["hybrid_score"] = round(0.7 * m["score"] + 0.3 * (b / max_bm), 4)

        matches = await self._rerank(query, matches, top_k)
        return [m for m in matches if m["score"] >= threshold][:top_k]

    async def _rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        """Re-ranking: Cohere Rerank (si COHERE_API_KEY) o fusión heurística local."""
        if settings.cohere_api_key:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        "https://api.cohere.ai/v1/rerank",
                        headers={"Authorization": f"Bearer {settings.cohere_api_key}"},
                        json={
                            "model": settings.cohere_rerank_model,
                            "query": query,
                            "documents": [c["content"][:2000] for c in candidates],
                            "top_n": min(top_k, len(candidates)),
                        },
                    )
                    resp.raise_for_status()
                    ranked: list[dict] = []
                    for r in resp.json().get("results", []):
                        cand = dict(candidates[r["index"]])
                        cand["rerank_score"] = round(float(r["relevance_score"]), 4)
                        ranked.append(cand)
                    ranked.sort(key=lambda c: c["rerank_score"], reverse=True)
                    return ranked
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cohere rerank falló (%s); usando heurístico.", exc)

        # Heurístico: bonus por coincidencia de términos con el nombre del archivo
        q_terms = set(_tokenize(query))
        for c in candidates:
            fname_terms = set(_tokenize(c["file_path"].replace("/", " ").replace(".", " ")))
            bonus = 0.02 * len(q_terms & fname_terms)
            hybrid = c.get("hybrid_score", c["score"])
            c["_final"] = 0.6 * c["score"] + 0.4 * hybrid + bonus
        candidates.sort(key=lambda x: x["_final"], reverse=True)
        for c in candidates:
            c.pop("_final", None)
        return candidates[:top_k]

    # -- Contexto y respuesta -------------------------------------------------------
    def build_context(self, chunks: list[dict[str, Any]]) -> str:
        """Formatea los chunks recuperados como bloque de contexto para el prompt."""
        if not chunks:
            return "(sin resultados relevantes en el repositorio)"
        blocks = []
        for c in chunks:
            meta = c.get("metadata", {})
            blocks.append(
                f"[Archivo: {c['file_path']}]\n"
                f"[Lenguaje: {meta.get('language', 'desconocido')}]\n\n"
                f"{c['content']}\n"
            )
        return "\n---\n\n".join(blocks)

    async def answer_question(
        self,
        query: str,
        use_repo_context: bool = True,
        conversation_history: Optional[list[dict[str, str]]] = None,
    ) -> dict[str, Any]:
        """Pipeline completo: retrieve -> context -> GPT-4o -> respuesta + citas.

        Cachea respuestas a preguntas idénticas (TTL 1 hora).
        """
        cached = self.answer_cache.get(query)
        if cached:
            return cached

        sources: list[dict[str, Any]] = []
        context = ""
        if use_repo_context:
            chunks = await self.search_repository(query, top_k=settings.rag_top_k_default)
            context = self.build_context(chunks)
            sources = [
                {
                    "file": c["file_path"],
                    "chunk_index": c.get("metadata", {}).get("chunk_index", 0),
                    "relevance_score": round(c["score"], 4),
                }
                for c in chunks
            ]

        messages: list[dict[str, str]] = list((conversation_history or [])[-10:])
        messages.append({
            "role": "user",
            "content": PROMPT_TEMPLATE.format(context=context, query=query),
        })

        resp = await self._openai.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=0.3,
            max_tokens=1200,
        )
        usage = resp.usage
        result = {
            "response": resp.choices[0].message.content or "",
            "sources": sources,
            "tokens_used": usage.total_tokens if usage else 0,
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "used_repo_context": use_repo_context,
            "cached": False,
        }
        self.answer_cache.set(query, result)
        return result

    # -- Métricas -------------------------------------------------------------------
    def index_stats(self) -> dict[str, Any]:
        try:
            desc = self.index.describe_index_stats()
            total = getattr(desc, "vector_count", None)
            if total is None:
                total = sum(
                    ns.get("vector_count", 0)
                    for ns in (getattr(desc, "namespaces", None) or {}).values()
                )
            return {
                "name": settings.pinecone_index_name,
                "ready": True,
                "total_vector_count": total,
                "dimension": settings.embedding_dimensions,
                "metric": "cosine",
            }
        except Exception as exc:  # noqa: BLE001
            return {"name": settings.pinecone_index_name, "ready": False, "error": str(exc)}

    def cache_stats(self) -> dict[str, Any]:
        return self.answer_cache.stats()


# Singleton usado por routers y scripts
rag_service = RAGService()
