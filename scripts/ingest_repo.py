#!/usr/bin/env python3
"""
ingest_repo.py — Script de ingesta vectorial del repositorio a Pinecone (Fase 5).

Pipeline completo:
  Paso 1: Lee los archivos del repo vía github_service + cache_service (Fase 4)
          (o desde el snapshot existente si está fresco).
  Paso 2: Chunking inteligente (~500 tokens, overlap 50) según el lenguaje:
          código por funciones/clases, markdown por secciones, resto por párrafos.
  Paso 3: Embeddings OpenAI text-embedding-3-small (1536 dims), batches de 100.
  Paso 4: Upsert al índice "jarvis-repo" (se crea si no existe, métrica cosine),
          con metadata completa y texto original.
  Paso 5: Actualización INCREMENTAL: compara commit_sha por archivo; omite los
          sin cambios, reprocesa los modificados y elimina los desaparecidos.

Uso:
    cd backend && python ../scripts/ingest_repo.py [--dry-run] [--force] [--max-files N]

    --dry-run : analiza y trocea sin llamar a OpenAI ni subir a Pinecone
    --force   : ignora el estado previo y re-procesa TODOS los archivos
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time

# Permite ejecutar el script desde backend/ sin instalar el paquete
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import settings  # noqa: E402
from app.services.cache_service import cache_service  # noqa: E402
from app.services.chunking_service import chunk_file, count_tokens  # noqa: E402
from app.services.github_service import github_service  # noqa: E402
from app.services.rag_service import RAGService, chunk_id  # noqa: E402

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    stream=sys.stdout,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("jarvis.ingest")


def _progress(update: dict) -> None:
    pct = ""
    if update.get("total"):
        pct = f" [{update['current']}/{update['total']} {update['current']/update['total']*100:.0f}%]"
    logger.info("%s%s → %s", update.get("phase", ""), pct, update.get("file", ""))


async def ingest(force: bool = False, dry_run: bool = False, max_files: int = 200) -> None:
    t0 = time.monotonic()
    await github_service.startup()
    try:
        # ---------------- Paso 1: obtener archivos del repositorio ----------
        logger.info("📡 Paso 1/5 — Obteniendo archivos de %s ...", settings.repo_full_name)
        snap = cache_service.get_snapshot()
        if force or not snap or snap.get("_expired"):
            cache_service.invalidate(reason="ingest_repo.py")
            metrics = await cache_service.sync_repo(github_service, max_files=max_files)
            logger.info(
                "   ✔ Sync GitHub: %d archivos en árbol, %d cacheados (%.2fs)",
                metrics["tree_files"], metrics["cached_files"], metrics["duration_seconds"],
            )
            snap = cache_service.get_snapshot()
        else:
            logger.info("   ✔ Usando snapshot de caché existente (%d archivos).",
                        len(snap.get("files", {})))
        if not snap or not snap.get("files"):
            logger.error("❌ Sin archivos para procesar. ¿Configuraste GITHUB_* en .env?")
            sys.exit(1)

        files: dict = snap["files"]

        # ---------------- Paso 2: chunking -----------------------------------
        logger.info("🧩 Paso 2/5 — Chunking (~%d tokens, overlap %d)...",
                    settings.rag_chunk_tokens, settings.rag_chunk_overlap_tokens)
        all_chunks: list[dict] = []
        for path, data in sorted(files.items()):
            chunks = chunk_file(
                path, data.get("content", ""),
                chunk_tokens=settings.rag_chunk_tokens,
                overlap_tokens=settings.rag_chunk_overlap_tokens,
            )
            for c in chunks:
                all_chunks.append({
                    "id": chunk_id(path, c.index),
                    "content": c.text,
                    "metadata": {
                        "file_path": path,
                        "chunk_index": c.index,
                        "total_chunks": c.total,
                        "language": c.metadata.get("language", "text"),
                        "folder": path.rsplit("/", 1)[0] if "/" in path else "",
                        "last_modified": data.get("last_modified", ""),
                        "commit_sha": data.get("sha", ""),
                        "repo": snap.get("repo", settings.repo_full_name),
                    },
                })
        avg = sum(count_tokens(c["content"]) for c in all_chunks) / max(1, len(all_chunks))
        logger.info("   ✔ %d chunks de %d archivos (media %.0f tokens/chunk)",
                    len(all_chunks), len(files), avg)

        if dry_run:
            sample = all_chunks[:3]
            for s in sample:
                logger.info("   ej: id=%s file=%s lang=%s", s["id"],
                            s["metadata"]["file_path"], s["metadata"]["language"])
            logger.info("🔎 Modo dry-run: no se llamaron APIs externas.")
            return

        # ---------------- Pasos 3+4+5: embeddings, upsert e incremental ------
        if not settings.pinecone_api_key:
            logger.error("❌ Falta PINECONE_API_KEY en el entorno (.env). Abortando.")
            sys.exit(1)
        if not settings.openai_api_key:
            logger.error("❌ Falta OPENAI_API_KEY en el entorno (.env). Abortando.")
            sys.exit(1)

        rag = RAGService()
        logger.info("🚀 Pasos 3-5 — Ingesta INCREMENTAL (embeddings + upsert a '%s')...",
                    settings.pinecone_index_name)
        result = await rag.ingest_from_snapshot(snap, force=force, progress_cb=_progress)

        stats = result["stats"]
        logger.info(
            "✅ Ingesta finalizada en %.1fs — añadidos:%d actualizados:%d omitidos:%d "
            "eliminados:%d chunks subidos:%d | estado:%s",
            time.monotonic() - t0,
            stats.get("added", 0), stats.get("updated", 0), stats.get("skipped", 0),
            stats.get("deleted", 0), stats.get("chunks_upserted", 0),
            result["status"],
        )
        if result["errors"]:
            logger.warning("⚠ Errores (%d): %s", len(result["errors"]),
                           "; ".join(result["errors"][:5]))
        index_stats = rag.index_stats()
        logger.info("📊 Índice: %s", index_stats)
    finally:
        await github_service.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Vectoriza el repo de GitHub en Pinecone (RAG Fase 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analiza y trocea sin llamar a OpenAI/Pinecone")
    parser.add_argument("--force", action="store_true",
                        help="Re-procesa todos los archivos (ignora la ingesta incremental)")
    parser.add_argument("--max-files", type=int, default=200,
                        help="Máximo de archivos a sincronizar/cachear")
    args = parser.parse_args()
    asyncio.run(ingest(force=args.force, dry_run=args.dry_run, max_files=args.max_files))
