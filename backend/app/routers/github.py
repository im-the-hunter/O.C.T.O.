"""
Routers de GitHub (Fase 4) — API pública del backend para el HUD.

Endpoints:
  GET  /api/github/status   -> estado de conexión, último sync, archivos cacheados
  GET  /api/github/tree     -> árbol completo (caché-first)
  GET  /api/github/file/{path}      -> contenido de un archivo (caché-first)
  GET  /api/github/commits          -> últimos N commits
  GET  /api/github/branch           -> info de la rama
  GET  /api/github/actions          -> estado del último workflow run
  GET  /api/github/cache            -> métricas de caché (hit rate, edad, TTL)
  POST /api/github/sync             -> sincronización manual (invalida + relee)
  POST /webhook/github              -> webhooks firmados de GitHub

Manejo de errores tipificado: 401 token inválido, 404 repo/archivo inexistente,
429 rate limit, 503 API de GitHub caída o configuración ausente.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request

from app.core.config import settings
from app.services.cache_service import cache_service
from app.services.github_service import (
    GitHubAPIError,
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubRateLimit,
    GitHubServiceError,
    github_service,
)

logger = logging.getLogger("jarvis.routers.github")

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _translate(exc: GitHubServiceError) -> HTTPException:
    """Convierte errores de dominio en HTTPExceptions con código adecuado."""
    return HTTPException(status_code=exc.status_code, detail=exc.message)


async def _snapshot(force_refresh: bool = False) -> dict[str, Any]:
    """Devuelve el snapshot de caché, sincronizando si está vacío/expirado."""
    if not force_refresh:
        snap = cache_service.get_snapshot()
        if snap and not snap.get("_expired"):
            return snap

    logger.info("Sincronizando repositorio (%s)...",
                "manual" if force_refresh else "cache miss/expirada")
    metrics = await cache_service.sync_repo(github_service)
    snap = cache_service.get_snapshot()
    if snap is None:  # pragma: no cover — tras set_snapshot no debería pasar
        raise HTTPException(status_code=503, detail="No se pudo construir la caché del repo.")
    snap["_sync_metrics"] = metrics
    return snap


def _verify_webhook_signature(payload_bytes: bytes, signature_header: Optional[str]) -> bool:
    """Valida X-Hub-Signature-256 con el secret compartido del webhook."""
    if not settings.github_webhook_secret:
        logger.warning("GITHUB_WEBHOOK_SECRET no definido: firma NO verificable.")
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.github_webhook_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)


async def _revectorize_background(reason: str) -> None:
    """Dispara la re-vectorización (Fase 5) tras un push o sync manual.

    Pipeline: invalidar caché GitHub -> resincronizar snapshot -> ingesta
    INCREMENTAL a Pinecone comparando commit_sha por archivo.
    """
    cache_service.invalidate(reason=f"webhook:{reason}")
    logger.info("Re-vectorización iniciada (%s).", reason)
    try:
        snap = await _snapshot(force_refresh=True)
        from app.services.rag_service import rag_service

        result = await rag_service.ingest_from_snapshot(snap, force=False)
        logger.info("Re-vectorización completada (%s): %s", reason, result["stats"])
    except Exception as exc:  # noqa: BLE001 — el webhook no debe fallar por RAG
        logger.error("Re-vectorización falló (%s): %s", reason, exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/status", summary="Estado de la integración con GitHub")
async def github_status() -> dict[str, Any]:
    """¿Conectado? ¿último sync? ¿cuántos archivos cacheados? ¿cuota restante?"""
    connected = github_service.configured
    cache_status = cache_service.status()
    result: dict[str, Any] = {
        "connected": connected,
        "repo": github_service.repo_full_name if connected else None,
        "branch": settings.github_branch,
        "last_sync": cache_status.get("last_sync"),
        "files_count": cache_status.get("files_cached", 0),
        "cache_status": cache_status.get("state", "empty"),
        "message": None,
    }
    if not connected:
        result["message"] = (
            "GitHub no configurado. Define GITHUB_TOKEN, GITHUB_REPO_OWNER y GITHUB_REPO_NAME."
        )
        return result

    try:
        result["rate_limit"] = await github_service.get_rate_limit()
    except GitHubServiceError as exc:
        result["message"] = exc.message
    return result


@router.get("/tree", summary="Árbol completo del repositorio (caché-first)")
async def get_tree(refresh: bool = Query(False, description="Fuerza re-sincronización")) -> dict[str, Any]:
    try:
        snap = await _snapshot(force_refresh=refresh)
    except GitHubServiceError as exc:
        raise _translate(exc) from exc
    tree = snap.get("repo_tree", {})
    tree["cached"] = not refresh
    tree["last_sync"] = snap.get("last_sync")
    return tree


@router.get("/file/{path:path}", summary="Contenido de un archivo (caché-first)")
async def get_file(
    path: str,
    refresh: bool = Query(False, description="Ignora la caché para este archivo"),
) -> dict[str, Any]:
    try:
        if not refresh:
            snap = cache_service.get_snapshot()
            if snap and not snap.get("_expired"):
                entry = snap.get("files", {}).get(path)
                if entry:
                    cache_service.hits += 0  # ya contabilizado en get_snapshot
                    return {
                        "path": path,
                        "content": entry["content"],
                        "sha": entry.get("sha"),
                        "size": entry.get("size"),
                        "source": "cache",
                        "last_sync": snap.get("last_sync"),
                    }
        # Cache miss → lectura directa a GitHub (y siguiente sync lo incluirá)
        content = await github_service.get_file_content(path)
        return {"path": path, "content": content, "source": "github"}
    except GitHubServiceError as exc:
        raise _translate(exc) from exc


@router.get("/commits", summary="Últimos N commits")
async def get_commits(n: int = Query(10, ge=1, le=100)) -> list[dict[str, Any]]:
    try:
        return await github_service.get_recent_commits(n=n)
    except GitHubServiceError as exc:
        raise _translate(exc) from exc


@router.get("/branch", summary="Información de la rama configurada")
async def get_branch() -> dict[str, Any]:
    try:
        return await github_service.get_branch_info()
    except GitHubServiceError as exc:
        raise _translate(exc) from exc


@router.get("/actions", summary="Estado del último workflow run (indicador HUD)")
async def get_actions() -> dict[str, Any]:
    try:
        return await github_service.get_github_actions_status()
    except GitHubServiceError as exc:
        raise _translate(exc) from exc


@router.get("/cache", summary="Métricas internas de la caché")
async def get_cache_metrics() -> dict[str, Any]:
    return cache_service.status()


@router.post("/sync", summary="Sincronización manual: invalida caché y relee todo")
async def force_sync(background_tasks: BackgroundTasks) -> dict[str, Any]:
    cache_service.invalidate(reason="POST /api/github/sync")
    try:
        metrics = await cache_service.sync_repo(github_service)
    except GitHubServiceError as exc:
        raise _translate(exc) from exc
    background_tasks.add_task(_revectorize_background, "manual-sync")
    return {
        "success": True,
        "duration_seconds": metrics["duration_seconds"],
        "tree_files": metrics["tree_files"],
        "cached_files": metrics["cached_files"],
        "commit_sha": metrics["commit_sha"],
        "message": "Repositorio sincronizado y caché reconstruida.",
    }


# ---------------------------------------------------------------------------
# Webhooks de GitHub (router aparte, montado en la raíz: POST /webhook/github)
# ---------------------------------------------------------------------------
webhook_router = APIRouter()


@webhook_router.post(
    "/webhook/github",
    summary="Webhook entrante de GitHub (push, pull_request, workflow_run...)",
)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
) -> dict[str, Any]:
    """Recibe eventos de GitHub. Valida la firma HMAC-SHA256.

    En eventos `push`: invalida la caché y encola la re-vectorización (Fase 5).
    """
    body = await request.body()

    if settings.github_webhook_secret:
        if not _verify_webhook_signature(body, x_hub_signature_256):
            logger.warning("Webhook rechazado: firma inválida o ausente.")
            raise HTTPException(status_code=401, detail="Firma del webhook inválida.")

    try:
        payload: dict[str, Any] = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Payload JSON inválido.") from exc

    event = x_github_event or "unknown"
    repo = (payload.get("repository") or {}).get("full_name")
    logger.info("Webhook recibido: event=%s repo=%s", event, repo)

    action_taken = "ignored"
    if event == "push":
        background_tasks.add_task(_revectorize_background, f"push:{repo}")
        action_taken = "cache_invalidated_revectorize_queued"
    elif event in ("pull_request", "workflow_run"):
        action_taken = "logged"

    return {"received": True, "event": event, "repo": repo, "action": action_taken}
