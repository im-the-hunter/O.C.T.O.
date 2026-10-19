"""
Endpoints de IA (Fase 5) — RAG sobre el repositorio + agente conversacional.

  POST /api/ai/chat            -> pregunta con contexto del repo (retrieve+GPT-4o)
  POST /api/ai/ingest          -> dispara ingesta (incremental o forzada), async
  GET  /api/ai/ingest/status   -> progreso en tiempo real (polling)
  GET  /api/ai/search          -> búsqueda directa de chunks (sin LLM)
  GET  /api/ai/stats           -> métricas de índice Pinecone + caché de respuestas
  GET  /api/ai/models          -> modelos configurados

Manejo de errores: 503 si Pinecone/OpenAI no están configurados o caen,
400 en parámetros inválidos. Todo documentado en Swagger (/docs).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.agent_service import AgentService
from app.services.cache_service import cache_service
from app.services.github_service import GitHubServiceError, github_service
from app.services.rag_service import rag_service

logger = logging.getLogger("jarvis.routers.ai")

router = APIRouter()
agent_service = AgentService()


# ---------------------------------------------------------------------------
# Modelos de petición/respuesta (Swagger-friendly)
# ---------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Pregunta del usuario")
    use_repo_context: bool = Field(True, description="Contextualizar con el repo (RAG)")
    conversation_history: list[ChatMessage] = Field(
        default_factory=list, description="Historial de la conversación (opcional)"
    )
    session_id: str = Field("default", description="Hilo de conversación del agente")
    top_k: int = Field(5, ge=1, le=20, description="Chunks recuperados del repo")


class Source(BaseModel):
    file: str
    chunk_index: int = 0
    relevance_score: float


class ChatResponse(BaseModel):
    response: str
    sources: list[Source] = []
    tokens_used: int = 0
    cached: bool = False
    used_repo_context: bool = True


class IngestRequest(BaseModel):
    force: bool = Field(False, description="Si es true, re-procesa todo desde cero")
    max_files: int = Field(200, ge=1, le=2000, description="Tope de archivos a sincronizar")


class IngestAccepted(BaseModel):
    accepted: bool
    status: str
    message: str


class SearchResponse(BaseModel):
    query: str
    results: list[dict[str, Any]]
    count: int
    threshold: float


# ---------------------------------------------------------------------------
# Estado de la ingesta en segundo plano (polling simple y robusto)
# ---------------------------------------------------------------------------
_ingest_progress: dict[str, Any] = {
    "status": "idle",       # idle | syncing | running | done | error
    "phase": "",
    "current": 0,
    "total": 0,
    "file": "",
    "stats": {},
    "errors": [],
}
_ingest_task: Optional[asyncio.Task] = None


def _progress_cb(update: dict[str, Any]) -> None:
    _ingest_progress.update(update)


async def _run_ingest(force: bool, max_files: int) -> None:
    """Tarea en background: sync GitHub (si hace falta) -> ingesta incremental."""
    global _ingest_progress
    try:
        _ingest_progress.update({"status": "syncing", "phase": "github_snapshot",
                                 "errors": [], "stats": {}})
        snap = cache_service.get_snapshot()
        if force or not snap or snap.get("_expired"):
            from app.services.cache_service import cache_service as cs
            cs.invalidate(reason="ingest:refresh")
            await cs.sync_repo(github_service, max_files=max_files)
            snap = cache_service.get_snapshot()
        if not snap:
            raise RuntimeError("No se pudo obtener el snapshot del repositorio.")

        _ingest_progress.update({"status": "running", "phase": "embedding_upsert"})
        result = await rag_service.ingest_from_snapshot(
            snap, force=force, progress_cb=_progress_cb
        )
        _ingest_progress.update({
            "status": "done" if result["status"] != "done_with_errors" else "done",
            "phase": "finished",
            "stats": result["stats"],
            "errors": result["errors"],
        })
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingesta en background falló")
        _ingest_progress.update({"status": "error", "phase": "failed",
                                 "errors": [str(exc)]})


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Conversación con JARVIS (RAG sobre el repo + GPT-4o)",
)
async def chat(request: ChatRequest) -> ChatResponse:
    """Responde usando contexto recuperado del repositorio vectorizado.

    - `use_repo_context=true`: retrieve (umbral >0.7) -> build_context -> GPT-4o.
    - Preguntas idénticas dentro del TTL (1h) se sirven desde caché.
    """
    history = [{"role": m.role, "content": m.content} for m in request.conversation_history]
    try:
        if request.use_repo_context:
            result = await rag_service.answer_question(
                query=request.message,
                use_repo_context=True,
                conversation_history=history,
            )
            return ChatResponse(**result)
        # Sin contexto de repo: respuesta directa del agente
        reply = await agent_service.run(
            user_message=request.message, context="", session_id=request.session_id
        )
        return ChatResponse(response=reply, sources=[], used_repo_context=False)
    except RuntimeError as exc:  # config ausente (OPENAI/PINECONE)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GitHubServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo en /api/ai/chat")
        raise HTTPException(status_code=500, detail=f"Fallo del pipeline RAG: {exc}") from exc


@router.post(
    "/ingest",
    response_model=IngestAccepted,
    status_code=202,
    summary="Dispara la ingesta vectorial del repositorio (asíncrona)",
)
async def start_ingest(request: IngestRequest, background_tasks: BackgroundTasks) -> IngestAccepted:
    """Lanza la ingesta en background. Progreso: GET /api/ai/ingest/status.

    Incremental por defecto: solo archivos cuyo commit_sha cambió respecto a
    lo ya almacenado en Pinecone. Con `force=true` reprocesa todo.
    """
    global _ingest_task
    if _ingest_task and not _ingest_task.done():
        return IngestAccepted(
            accepted=False, status="running",
            message="Ya hay una ingesta en curso; consulta /api/ai/ingest/status.",
        )
    _ingest_progress.update({"status": "queued", "phase": "queued", "errors": [], "stats": {}})
    _ingest_task = asyncio.create_task(_run_ingest(request.force, request.max_files))
    background_tasks.add_task(lambda: None)  # mantiene compatibilidad con test clients
    return IngestAccepted(
        accepted=True, status="queued",
        message=f"Ingesta {'completa (force)' if request.force else 'incremental'} iniciada.",
    )


@router.get(
    "/ingest/status",
    summary="Progreso en tiempo real de la ingesta (polling)",
)
async def ingest_status() -> dict[str, Any]:
    return {**_ingest_progress, "rag_last_ingest": rag_service.last_ingest}


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Búsqueda directa en el repositorio (sin generar respuesta)",
)
async def search(
    q: str = Query(..., min_length=2, description="Texto a buscar semánticamente"),
    top_k: int = Query(5, ge=1, le=20),
    min_score: Optional[float] = Query(None, ge=0.0, le=1.0,
                                       description="Umbral (default 0.7)"),
    language: Optional[str] = Query(None, description="Filtro por lenguaje (p.ej. python)"),
    folder: Optional[str] = Query(None, description="Filtro por prefijo de carpeta"),
    include_content: bool = Query(False, description="Incluir el texto del chunk"),
) -> SearchResponse:
    """Hybrid search: vectorial + BM25 + re-ranking, con filtros de metadata."""
    try:
        chunks = await rag_service.search_repository(
            q, top_k=top_k, min_score=min_score,
            language=language, folder_prefix=folder,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    results = []
    for c in chunks:
        item = {
            "id": c["id"],
            "file_path": c["file_path"],
            "score": round(c["score"], 4),
            "bm25_score": c.get("bm25_score"),
            "hybrid_score": c.get("hybrid_score"),
            "metadata": {k: v for k, v in c["metadata"].items() if k != "text"},
        }
        if include_content:
            item["content"] = c["content"]
        results.append(item)
    return SearchResponse(
        query=q, results=results, count=len(results),
        threshold=settings.rag_min_score if min_score is None else min_score,
    )


@router.get("/stats", summary="Métricas del índice vectorial y de la caché de respuestas")
async def stats() -> dict[str, Any]:
    try:
        index = rag_service.index_stats()
    except RuntimeError as exc:
        index = {"ready": False, "error": str(exc)}
    return {
        "pinecone": index,
        "answer_cache": rag_service.cache_stats(),
        "last_ingest": rag_service.last_ingest,
        "chunking": {
            "chunk_tokens": settings.rag_chunk_tokens,
            "overlap_tokens": settings.rag_chunk_overlap_tokens,
        },
        "reranker": "cohere" if settings.cohere_api_key else "heuristic+bm25",
    }


@router.get("/models", summary="Modelos configurados en el sistema")
async def list_models() -> dict[str, Any]:
    return {
        "chat": settings.openai_model,
        "embeddings": settings.openai_embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "pinecone_index": settings.pinecone_index_name,
        "rerank_model": settings.cohere_rerank_model if settings.cohere_api_key else None,
    }
