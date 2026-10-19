"""Endpoints de GitHub: info del repo, commits, archivos y PRs."""
from fastapi import APIRouter, HTTPException, Query

from app.services.github_service import GitHubService

router = APIRouter()
github_service = GitHubService()


@router.get("/repo")
async def get_repo_info():
    """Metadatos básicos del repositorio configurado."""
    try:
        return await github_service.get_repo_info()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/commits")
async def list_commits(limit: int = Query(20, ge=1, le=100)):
    """Lista los últimos commits del repositorio."""
    try:
        return await github_service.list_commits(limit=limit)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/file/{path:path}")
async def get_file(path: str):
    """Devuelve el contenido de un archivo del repositorio."""
    content = await github_service.get_file_content(path)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {path}")
    return {"path": path, "content": content}
