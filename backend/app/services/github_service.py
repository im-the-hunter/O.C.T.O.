"""
Servicio de GitHub: lectura de repositorio, commits y archivos.
Usa PyGithub de forma asíncrona vía thread pool para no bloquear el event loop.
"""
import asyncio
from functools import partial
from typing import Any, Optional

from github import Github
from github.Repository import Repository

from app.core.config import settings


class GitHubService:
    def __init__(self) -> None:
        self._client = Github(settings.github_token)
        self._owner = settings.github_repo_owner
        self._name = settings.github_repo_name

    @property
    def repo(self) -> Repository:
        return self._client.get_repo(f"{self._owner}/{self._name}")

    async def _run(self, func, *args, **kwargs) -> Any:
        """Ejecuta una llamada síncrona de PyGithub en un hilo aparte."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def get_repo_info(self) -> dict:
        repo = await self._run(lambda: self.repo)
        return {
            "full_name": repo.full_name,
            "description": repo.description,
            "default_branch": repo.default_branch,
            "stars": repo.stargazers_count,
            "forks": repo.forks_count,
            "language": repo.language,
            "updated_at": repo.updated_at.isoformat(),
        }

    async def list_commits(self, limit: int = 20) -> list[dict]:
        def _fetch():
            repo = self.repo
            return [
                {
                    "sha": c.sha[:7],
                    "message": c.commit.message.splitlines()[0],
                    "author": c.commit.author.name,
                    "date": c.commit.author.date.isoformat(),
                }
                for c in repo.get_commits()[:limit]
            ]

        return await self._run(_fetch)

    async def get_file_content(self, path: str) -> Optional[str]:
        def _fetch():
            try:
                return self.repo.get_contents(path).decoded_content.decode("utf-8")
            except Exception:
                return None

        return await self._run(_fetch)

    async def list_python_files(self) -> list[str]:
        """Lista rutas de archivos de código (para la ingesta vectorial)."""
        def _fetch():
            tree = self.repo.get_git_tree(
                self.repo.default_branch, recursive=True
            ).tree
            exts = (".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".sql", ".yaml", ".yml")
            return [t.path for t in tree if t.type == "blob" and t.path.endswith(exts)]

        return await self._run(_fetch)
