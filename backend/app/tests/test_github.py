#!/usr/bin/env python3
"""
test_github.py — Verificación de la integración GitHub + caché (Fase 4).

Uso:
    cd backend && python -m app.tests.test_github            # smoke test completo
    cd backend && python -m app.tests.test_github --offline  # solo lógica sin red

Comprueba:
 1. Validación de configuración (.env)
 2. Autenticación contra la API de GitHub (GET /rate_limit con token)
 3. Lectura del árbol del repo, branch, commits y Actions status
 4. Sistema de caché: sync -> snapshot -> hit (0 llamadas extra) -> invalidación
 5. Filtrado de archivos (binarios/node_modules/1MB)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time

# Asegura que `backend/` esté en el path cuando se ejecuta como script suelto
sys.path.insert(0, ".")

from app.core.config import settings, validate_required_settings  # noqa: E402
from app.services import github_service as gs  # noqa: E402
from app.services.cache_service import cache_service  # noqa: E402


PASS = "\033[92m✔\033[0m"
FAIL = "\033[91m✘\033[0m"


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{PASS if ok else FAIL}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def test_filtering() -> bool:
    print("\n[5] Filtrado de archivos")
    results = []
    results.append(check("ignora node_modules", not gs.is_ingestible("node_modules/x/index.js", 10)))
    results.append(check("ignora .git/", not gs.is_ingestible(".git/config", 10)))
    results.append(check("ignora __pycache__", not gs.is_ingestible("app/__pycache__/x.pyc", 10)))
    results.append(check("ignora dist/build", not gs.is_ingestible("dist/bundle.js", 10)))
    results.append(check("ignora binarios (.png)", not gs.is_ingestible("public/logo.png", 10)))
    results.append(check("rechaza >1MB", not gs.is_ingestible("big.py", gs.MAX_FILE_SIZE_BYTES + 1)))
    results.append(check("acepta .ts/.tsx/.py/.md", all([
        gs.is_ingestible("a.ts", 10), gs.is_ingestible("b.tsx", 10),
        gs.is_ingestible("c.py", 10), gs.is_ingestible("d.md", 10),
    ])))
    return all(results)


async def test_online() -> bool:
    service = gs.GitHubService()
    await service.startup()
    results = []
    try:
        print("\n[1] Configuración")
        missing = validate_required_settings()
        gh_missing = [m for m in missing if m.startswith("GITHUB")]
        if not check("variables GitHub presentes", not gh_missing,
                     ", ".join(gh_missing) or service.repo_full_name):
            return False

        print("\n[2] Autenticación / cuota")
        t0 = time.monotonic()
        rl = await service.get_rate_limit()
        results.append(check("token válido (GET /rate_limit)", rl["limit"] > 0,
                             f"{rl['remaining']}/{rl['limit']} restantes, {time.monotonic()-t0:.2f}s"))

        print("\n[3] Lectura del repositorio")
        tree = await service.get_repo_tree()
        results.append(check("get_repo_tree()", len(tree.entries) > 0,
                             f"{len(tree.entries)} archivos, {len(tree.code_files)} ingestibles"))
        branch = await service.get_branch_info()
        results.append(check("get_branch_info()", branch["name"] == settings.github_branch,
                             f"HEAD {branch['sha'][:7]} por {branch['last_commit']['author']}"))
        commits = await service.get_recent_commits(5)
        results.append(check("get_recent_commits(5)", len(commits) > 0,
                             commits[0]["message"][:50] if commits else ""))
        actions = await service.get_github_actions_status()
        results.append(check("get_github_actions_status()", True,
                             f"badge={actions['badge']} status={actions['status']}"))
        if tree.code_files:
            first = tree.code_files[0].path
            content = await service.get_file_content(first)
            results.append(check(f"get_file_content('{first}')", len(content) > 0,
                                 f"{len(content)} chars"))

        print("\n[4] Caché: sync + hit rate")
        metrics = await cache_service.sync_repo(service)
        results.append(check("sync_repo()", metrics["cached_files"] >= 0,
                             f"{metrics['duration_seconds']}s, {metrics['cached_files']} archivos cacheados"))
        snap = cache_service.get_snapshot()
        results.append(check("snapshot recuperado de disco", snap is not None,
                             f"estado={cache_service.status()['state']}"))
        # Relecturas: deben ser HITs (sin llamadas a GitHub)
        before = cache_service.hits
        for _ in range(5):
            cache_service.get_snapshot()
        results.append(check("5 relecturas → 5 hits de caché", cache_service.hits - before == 5,
                             f"hit rate global: {cache_service.status()['hit_rate_percent']}%"))
        cache_service.invalidate("test")
        results.append(check("invalidación manual", cache_service.get_snapshot() is None))
    finally:
        await service.shutdown()
    return all(results)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test GitHub J.A.R.V.I.S.")
    parser.add_argument("--offline", action="store_true",
                        help="Solo pruebas de lógica local (sin red/token)")
    args = parser.parse_args()

    print("=" * 60)
    print("  J.A.R.V.I.S. — Test de integración GitHub + Caché (Fase 4)")
    print("=" * 60)

    ok = test_filtering()
    if not args.offline:
        ok = asyncio.run(test_online()) and ok

    print("\n" + "=" * 60)
    print("  RESULTADO:", "TODO OK ✔" if ok else "HAY FALLOS ✘")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
