"""
Servicio de GitHub para Project J.A.R.V.I.S. (Fase 4).

Estrategia:
- Un único httpx.AsyncClient reutilizable con auth por Bearer token.
- Llamadas 100% asíncronas (async/await) — sin bloquear el event loop.
- Errores tipificados (GitHubAuthError / GitHubNotFound / GitHubRateLimit /
  GitHubAPIError) que el router traduce a 401 / 404 / 429 / 503.
- Filtrado inteligente de archivos: ignora binarios, node_modules, .git,
  __pycache__, dist, build... y limita el tamaño a 1 MB.
"""
from __future__ import annotations

import base64
import logging
import posixpath
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("jarvis.github")

GITHUB_API_BASE = "https://api.github.com"

# Carpetas que nunca deben indexarse ni leerse
IGNORED_DIRECTORIES = {
    "node_modules", ".git", "__pycache__", "dist", "build", ".next",
    ".venv", "venv", "env", ".cache", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "vendor", ".turbo",
}

# Extensiones de código/documentación priorizadas
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".json",
    ".yaml", ".yml", ".sql", ".sh", ".css", ".html",
}

# Extensiones claramente binarias (filtro rápido antes de mirar el size)
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff",
    ".mp3", ".wav", ".ogg", ".flac", ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".pdf", ".doc", ".docx",
    ".xls", ".xlsx", ".ppt", ".pptx", ".woff", ".woff2", ".ttf", ".eot",
    ".so", ".dll", ".dylib", ".exe", ".bin", ".o", ".a", ".pyc", ".pyd",
    ".class", ".jar", ".lockb",
}

MAX_FILE_SIZE_BYTES = settings.max_file_size_bytes  # 1 MB


# ---------------------------------------------------------------------------
# Excepciones de dominio
# ---------------------------------------------------------------------------
class GitHubServiceError(Exception):
    """Error base del servicio de GitHub."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class GitHubNotConfigured(GitHubServiceError):
    def __init__(self, missing: list[str]) -> None:
        super().__init__(
            f"Faltan variables de entorno de GitHub: {', '.join(missing)}",
            status_code=503,
        )


class GitHubAuthError(GitHubServiceError):
    def __init__(self) -> None:
        super().__init__("Token de GitHub inválido o sin permisos.", status_code=401)


class GitHubNotFoundError(GitHubServiceError):
    def __init__(self, what: str) -> None:
        super().__init__(f"No encontrado en GitHub: {what}", status_code=404)


class GitHubRateLimit(GitHubServiceError):
    def __init__(self, reset_at: Optional[str] = None) -> None:
        msg = "Rate limit de GitHub API superado."
        if reset_at:
            msg += f" Se restablece en {reset_at}."
        super().__init__(msg, status_code=429)


class GitHubAPIError(GitHubServiceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503)


# ---------------------------------------------------------------------------
# Modelos ligeros
# ---------------------------------------------------------------------------
@dataclass
class FileEntry:
    path: str
    size: int
    sha: str


@dataclass
class RepoTree:
    entries: list[FileEntry] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    branch: str = ""
    commit_sha: str = ""

    @property
    def code_files(self) -> list[FileEntry]:
        return [e for e in self.entries if is_ingestible(e.path, e.size)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "file_count": len(self.entries),
            "ingestible_count": len(self.code_files),
            "directories": self.directories,
            "files": [e.__dict__ for e in self.entries],
        }


# ---------------------------------------------------------------------------
# Utilidades de filtrado
# ---------------------------------------------------------------------------
_EXT_RE = re.compile(r"\.([A-Za-z0-9]+)$")


def _extension(path: str) -> str:
    m = _EXT_RE.search(posixpath.basename(path))
    return f".{m.group(1).lower()}" if m else ""


def is_ignored_path(path: str) -> bool:
    parts = set(path.split("/"))
    return bool(parts & IGNORED_DIRECTORIES)


def is_binary_path(path: str) -> bool:
    ext = _extension(path)
    if ext in BINARY_EXTENSIONS:
        return True
    if ext and ext not in CODE_EXTENSIONS:
        # extensión desconocida: se permite solo si además es texto razonable
        # (el filtro de tamaño lo acota); los conocidos binarios ya se excluyeron
        return False
    return False


def is_ingestible(path: str, size: int) -> bool:
    """Archivo apto para lectura/vectorización."""
    if is_ignored_path(path) or is_binary_path(path):
        return False
    return size <= MAX_FILE_SIZE_BYTES


# ---------------------------------------------------------------------------
# Servicio principal
# ---------------------------------------------------------------------------
class GitHubService:
    """Cliente asíncrono de la REST API v3 de GitHub para un repo concreto."""

    def __init__(self) -> None:
        self._owner = settings.github_repo_owner
        self._name = settings.github_repo_name
        self._branch = settings.github_branch
        self._token = settings.github_token
        self._client: Optional[httpx.AsyncClient] = None

    # -- ciclo de vida ------------------------------------------------------
    async def startup(self) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "project-jarvis-backend",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API_BASE,
            headers=headers,
            timeout=httpx.Timeout(20.0, connect=10.0),
            follow_redirects=True,
        )
        missing = [n for n, v in {
            "GITHUB_TOKEN": self._token,
            "GITHUB_REPO_OWNER": self._owner,
            "GITHUB_REPO_NAME": self._name,
        }.items() if not v]
        if missing:
            logger.warning("Config de GitHub incompleta: %s", ", ".join(missing))
        else:
            logger.info("GitHubService inicializado para %s/%s", self._owner, self._name)

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def configured(self) -> bool:
        return bool(self._token and self._owner and self._name)

    @property
    def repo_full_name(self) -> str:
        return f"{self._owner}/{self._name}"

    def _ensure_configured(self) -> None:
        if not self.configured:
            raise GitHubNotConfigured(
                [n for n, v in {
                    "GITHUB_TOKEN": self._token,
                    "GITHUB_REPO_OWNER": self._owner,
                    "GITHUB_REPO_NAME": self._name,
                }.items() if not v]
            )

    # -- HTTP base ------------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        self._ensure_configured()
        assert self._client is not None, "GitHubService no inicializado (startup)"
        try:
            resp = await self._client.request(method, path, params=params)
        except httpx.HTTPError as exc:
            raise GitHubAPIError(f"Fallo de red al llamar a GitHub: {exc}") from exc

        if resp.status_code == 401 or (resp.status_code == 403 and "Bad credentials" in resp.text):
            raise GitHubAuthError()
        if resp.status_code in (403, 429) and _is_rate_limit(resp):
            raise GitHubRateLimit(resp.headers.get("x-ratelimit-reset"))
        if resp.status_code == 404:
            raise GitHubNotFoundError(path)
        if resp.status_code >= 400:
            raise GitHubAPIError(
                f"GitHub API {resp.status_code} en {method} {path}: {resp.text[:300]}"
            )
        return resp

    async def _get_json(self, path: str, params: Optional[dict] = None) -> Any:
        resp = await self._request("GET", path, params=params)
        return resp.json()

    # -- Funcionales ----------------------------------------------------------
    async def get_repo_tree(self, branch: Optional[str] = None) -> RepoTree:
        """Árbol COMPLETO (recursivo) de archivos y carpetas del repo."""
        target_branch = branch or self._branch
        info = await self.get_branch_info(target_branch)
        sha = info["commit"]["sha"] if "commit" in info else info["sha"]
        data = await self._get_json(
            f"/repos/{self.repo_full_name}/git/trees/{sha}", {"recursive": "1"}
        )

        entries: list[FileEntry] = []
        dirs: set[str] = set()
        for item in data.get("tree", []):
            if item["type"] == "tree":
                if not is_ignored_path(item["path"]):
                    dirs.add(item["path"])
            elif item["type"] == "blob":
                if not is_ignored_path(item["path"]):
                    entries.append(FileEntry(
                        path=item["path"],
                        size=int(item.get("size", 0)),
                        sha=item.get("sha", ""),
                    ))
        tree = RepoTree(entries=entries, directories=sorted(dirs),
                        branch=target_branch, commit_sha=sha)
        logger.debug("Árbol de %s: %d archivos (%d ingestibles)",
                     self.repo_full_name, len(entries), len(tree.code_files))
        return tree

    async def get_file_content(self, file_path: str) -> str:
        """Contenido decodificado (UTF-8) de un archivo específico."""
        if is_ignored_path(file_path):
            raise GitHubNotFoundError(f"ruta ignorada por política: {file_path}")
        data = await self._get_json(
            f"/repos/{self.repo_full_name}/contents/{file_path}",
            {"ref": self._branch},
        )
        if isinstance(data, list):
            raise GitHubNotFoundError(f"{file_path} es un directorio")
        size = int(data.get("size", 0))
        if size > MAX_FILE_SIZE_BYTES:
            raise GitHubAPIError(
                f"Archivo demasiado grande ({size} bytes > límite {MAX_FILE_SIZE_BYTES}): {file_path}"
            )
        content_b64 = data.get("content", "")
        try:
            return base64.b64decode(content_b64).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            raise GitHubAPIError(f"El archivo {file_path} parece binario o corrupto") from exc

    async def get_recent_commits(self, n: int = 10) -> list[dict[str, Any]]:
        """Últimos N commits de la rama configurada."""
        data = await self._get_json(
            f"/repos/{self.repo_full_name}/commits",
            {"sha": self._branch, "per_page": max(1, min(n, 100))},
        )
        return [
            {
                "sha": c["sha"],
                "short_sha": c["sha"][:7],
                "message": c["commit"]["message"].splitlines()[0],
                "author": (c.get("commit", {}).get("author") or {}).get("name", "desconocido"),
                "date": (c.get("commit", {}).get("author") or {}).get("date"),
                "url": c["html_url"],
            }
            for c in data
        ]

    async def get_branch_info(self, branch: Optional[str] = None) -> dict[str, Any]:
        """Información de la rama (por defecto, la configurada)."""
        target = branch or self._branch
        data = await self._get_json(f"/repos/{self.repo_full_name}/branches/{target}")
        commit = data["commit"]
        return {
            "name": data["name"],
            "protected": data.get("protected", False),
            "sha": commit["sha"],
            "last_commit": {
                "sha": commit["sha"][:7],
                "message": commit["commit"]["message"].splitlines()[0],
                "author": commit["commit"]["author"]["name"],
                "date": commit["commit"]["author"]["date"],
            },
        }

    async def get_github_actions_status(self) -> dict[str, Any]:
        """Estado del último workflow run (para el indicador del HUD)."""
        data = await self._get_json(
            f"/repos/{self.repo_full_name}/actions/runs",
            {"per_page": 1, "branch": self._branch},
        )
        runs = data.get("workflow_runs", [])
        if not runs:
            return {"has_runs": False, "status": "none", "conclusion": None,
                    "workflow": None, "html_url": None, "updated_at": None,
                    "badge": "none"}
        run = runs[0]
        return {
            "has_runs": True,
            "status": run["status"],               # queued|in_progress|completed
            "conclusion": run.get("conclusion"),   # success|failure|cancelled|...
            "workflow": run["name"],
            "run_number": run["run_number"],
            "html_url": run["html_url"],
            "updated_at": run["updated_at"],
            # normalizado para el HUD: green / red / amber
            "badge": _actions_badge(run),
        }

    async def get_rate_limit(self) -> dict[str, Any]:
        """Resto de cuota de la API — útil para el panel de estado."""
        data = await self._get_json("/rate_limit")
        core = data.get("resources", {}).get("core", {})
        limit = int(core.get("limit", 0) or 0)
        remaining = int(core.get("remaining", 0) or 0)
        return {
            "limit": limit,
            "remaining": remaining,
            "used_percent": round((limit - remaining) / limit * 100, 1) if limit else 0.0,
            "reset": core.get("reset"),
        }


def _is_rate_limit(resp: httpx.Response) -> bool:
    remaining = resp.headers.get("x-ratelimit-remaining")
    return remaining == "0"


def _actions_badge(run: dict[str, Any]) -> str:
    if run["status"] != "completed":
        return "amber"
    return "green" if run.get("conclusion") == "success" else "red"


# Singleton usado por routers y servicios
github_service = GitHubService()
