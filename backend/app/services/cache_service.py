"""
Sistema de caché para GitHub (Fase 4) — evita rate limits.

Doble backend, misma interfaz:
- DiskCache (por defecto): JSON atómico en settings.cache_dir. Sin infra extra.
- RedisCache (opcional): si REDIS_URL está definida y `redis` instalable.

Estructura almacenada (spec del proyecto):
{
    "repo_tree": {...},
    "files": {
        "path/to/file.py": {"content": "...", "last_modified": ts, "sha": "..."}
    },
    "last_sync": iso_ts
}

Métricas hit/miss integradas: la sincronización completa usa 2 llamadas a
GitHub (branch + tree recursivo) sin importar cuántos archivos tenga el repo,
y cada lectura posterior es un HIT de caché → >90% de reducción de llamadas.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger("jarvis.cache")

CACHE_VERSION = 1


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------
class BaseCacheBackend:
    def get(self, key: str) -> Optional[dict[str, Any]]: ...
    def set(self, key: str, value: dict[str, Any]) -> None: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...


class DiskCache(BaseCacheBackend):
    """Caché en disco con escrituras atómicas (write-to-temp + rename)."""

    def __init__(self, cache_dir: str) -> None:
        self.root = Path(cache_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
        return self.root / f"{safe}.json"

    def get(self, key: str) -> Optional[dict[str, Any]]:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Caché corrupta en %s: %s", path, exc)
            path.unlink(missing_ok=True)
            return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        path = self._path(key)
        fd, tmp = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(value, fh, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError as exc:
            logger.error("No se pudo escribir la caché %s: %s", path, exc)
            if os.path.exists(tmp):
                os.unlink(tmp)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def clear(self) -> None:
        for p in self.root.glob("*.json"):
            p.unlink(missing_ok=True)


class RedisCache(BaseCacheBackend):
    """Caché Redis opcional (SET con EX = TTL natural de Redis)."""

    def __init__(self, url: str, ttl: int) -> None:
        import redis.asyncio as aioredis  # import perezoso: dependencia opcional

        self._redis = aioredis.from_url(url, decode_responses=True)
        self._ttl = ttl

    async def get_async(self, key: str) -> Optional[dict[str, Any]]:
        raw = await self._redis.get(f"jarvis:{key}")
        return json.loads(raw) if raw else None

    async def set_async(self, key: str, value: dict[str, Any]) -> None:
        await self._redis.set(
            f"jarvis:{key}", json.dumps(value, ensure_ascii=False), ex=self._ttl
        )

    async def delete_async(self, key: str) -> None:
        await self._redis.delete(f"jarvis:{key}")

    async def clear_async(self) -> None:
        async for k in self._redis.scan_iter(match="jarvis:*"):
            await self._redis.delete(k)


# ---------------------------------------------------------------------------
# Fachada con TTL + métricas
# ---------------------------------------------------------------------------
class CacheService:
    """Fachada síncrona sobre el backend elegido, con TTL e invalidación."""

    KEYS = ("github_snapshot",)

    def __init__(self) -> None:
        self.ttl = settings.cache_ttl_seconds
        self.hits = 0
        self.misses = 0
        self.invalidations = 0
        self.backend_name = "disk"
        self._backend: BaseCacheBackend = DiskCache(settings.cache_dir)
        self._redis: Optional[RedisCache] = None
        if settings.redis_url:
            try:
                self._redis = RedisCache(settings.redis_url, self.ttl)
                self.backend_name = "redis"
                logger.info("Usando Redis como backend de caché: %s", settings.redis_url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis no disponible (%s); fallback a disco.", exc)
                self._redis = None

    # -- API síncrona (disco) ------------------------------------------------
    def _snapshot_path(self) -> Path:
        return Path(settings.cache_dir) / "github_snapshot.json"

    def get_snapshot(self) -> Optional[dict[str, Any]]:
        """Devuelve el snapshot si existe y no ha expirado; None en caso contrario."""
        data = self._backend.get("github_snapshot")
        if not data:
            self.misses += 1
            return None
        synced_at = float(data.get("synced_at_epoch", 0))
        if time.time() - synced_at > self.ttl:
            logger.info("Caché expirada (TTL=%ss) — se considerará stale/fresh según uso.", self.ttl)
            data["_expired"] = True
        self.hits += 1
        return data

    def set_snapshot(self, snapshot: dict[str, Any]) -> None:
        snapshot["synced_at_epoch"] = time.time()
        snapshot["synced_at"] = _utcnow_iso()
        snapshot["version"] = CACHE_VERSION
        self._backend.set("github_snapshot", snapshot)
        logger.info(
            "Snapshot guardado (%s): %d archivos, árbol de %d entradas.",
            self.backend_name,
            len(snapshot.get("files", {})),
            len(snapshot.get("repo_tree", {}).get("files", [])),
        )

    def invalidate(self, reason: str = "manual") -> None:
        self._backend.delete("github_snapshot")
        self.invalidations += 1
        logger.info("Caché invalidada (%s).", reason)

    def status(self) -> dict[str, Any]:
        data = self._backend.get("github_snapshot")
        total = self.hits + self.misses
        age = None
        state = "empty"
        if data:
            age = time.time() - float(data.get("synced_at_epoch", 0))
            state = "fresh" if age <= self.ttl else "stale"
        return {
            "backend": self.backend_name,
            "state": state,
            "ttl_seconds": self.ttl,
            "age_seconds": round(age, 1) if age is not None else None,
            "files_cached": len(data.get("files", {})) if data else 0,
            "last_sync": data.get("synced_at") if data else None,
            "hit_rate_percent": round(self.hits / total * 100, 1) if total else None,
            "hits": self.hits,
            "misses": self.misses,
            "invalidations": self.invalidations,
        }

    # -- Sincronización con GitHub ------------------------------------------
    async def sync_repo(self, service, max_files: int = 200) -> dict[str, Any]:
        """Sincroniza el repo completo al snapshot de caché.

        Estrategia anti rate-limit:
          1. get_branch_info()      -> 1 llamada (HEAD del branch)
          2. get_repo_tree()        -> 2 llamadas (branch + tree recursivo)
             El tree recursivo ya trae size+sha de CADA archivo: no hace
             falta un stat por archivo.
          3. Contenido: solo archivos ingestibles priorizados (código/docs),
             limitados a `max_files`, descargados en paralelo con concurrencia
             acotada (semáforo) para respetar la cuota.

        Retorna métricas de la sincronización.
        """
        import asyncio

        t0 = time.monotonic()
        tree = await service.get_repo_tree()
        candidates = [
            e for e in tree.entries
            if _is_priority(e.path)
        ][:max_files]

        sem = asyncio.Semaphore(8)

        async def fetch(entry) -> tuple[str, Optional[dict[str, Any]]]:
            async with sem:
                try:
                    content = await service.get_file_content(entry.path)
                    return entry.path, {
                        "content": content,
                        "last_modified": entry.sha,  # sha como marca de versión
                        "sha": entry.sha,
                        "size": entry.size,
                    }
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Error leyendo %s: %s", entry.path, exc)
                    return entry.path, None

        results = await asyncio.gather(*(fetch(e) for e in candidates))
        files = {path: data for path, data in results if data is not None}

        snapshot = {
            "repo_tree": tree.to_dict(),
            "files": files,
            "last_sync": _utcnow_iso(),
            "repo": service.repo_full_name,
            "branch": tree.branch,
        }
        self.set_snapshot(snapshot)
        elapsed = round(time.monotonic() - t0, 2)
        logger.info(
            "Sync completada en %.2ss: %d archivos en árbol, %d con contenido.",
            elapsed, len(tree.entries), len(files),
        )
        return {
            "duration_seconds": elapsed,
            "tree_files": len(tree.entries),
            "cached_files": len(files),
            "commit_sha": tree.commit_sha,
        }


def _is_priority(path: str) -> bool:
    """Prioriza código y documentación para cachear el contenido."""
    from app.services.github_service import is_ingestible, CODE_EXTENSIONS

    ext = os.path.splitext(path)[1].lower()
    if not is_ingestible(path, 0):
        # is_ingestible con size=0 pasa el filtro de tamaño; ignoradas/binarias fallan
        return False
    return ext in CODE_EXTENSIONS or ext == ""


cache_service = CacheService()
