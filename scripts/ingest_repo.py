#!/usr/bin/env python3
"""
Script de ingesta vectorial: descarga los archivos del repositorio GitHub
configurado, los trocea (chunking) y los sube a Pinecone como vectores.

Uso:
    cd backend && python ../scripts/ingest_repo.py [--dry-run]
"""
import argparse
import asyncio
import hashlib
import os
import sys

# Permite ejecutar el script desde backend/ sin instalar el paquete
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import settings  # noqa: E402
from app.services.github_service import GitHubService  # noqa: E402
from app.services.rag_service import RAGService  # noqa: E402

CHUNK_SIZE = 1500  # caracteres por fragmento
CHUNK_OVERLAP = 200


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Trocea el texto en fragmentos con solapamiento."""
    if len(text) <= size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += size - overlap
    return chunks


async def ingest(dry_run: bool = False) -> None:
    gh = GitHubService()
    rag = RAGService()

    print(f"📡 Conectando con {settings.github_repo_owner}/{settings.github_repo_name} ...")
    files = await gh.list_python_files()
    print(f"🗂️  {len(files)} archivos candidatos a vectorización.")

    docs: list[dict] = []
    for path in files:
        content = await gh.get_file_content(path)
        if not content or not content.strip():
            continue
        for i, chunk in enumerate(chunk_text(content)):
            doc_id = hashlib.sha1(f"{path}:{i}".encode()).hexdigest()
            docs.append(
                {
                    "id": doc_id,
                    "content": chunk,
                    "metadata": {"source": path, "chunk": i, "repo": f"{settings.github_repo_owner}/{settings.github_repo_name}"},
                }
            )
        print(f"   ✔ {path}")

    print(f"🧩 Total de fragmentos: {len(docs)}")

    if dry_run:
        print("🔎 Modo dry-run: no se subió nada a Pinecone.")
        return

    if not settings.pinecone_api_key:
        print("❌ Falta PINECONE_API_KEY en el entorno (.env). Abortando.")
        sys.exit(1)

    uploaded = await rag.upsert_documents(docs)
    print(f"🚀 {uploaded} vectores subidos al índice '{settings.pinecone_index_name}'. Ingesta completa.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vectoriza el repo de GitHub en Pinecone")
    parser.add_argument("--dry-run", action="store_true", help="Analiza sin subir a Pinecone")
    args = parser.parse_args()
    asyncio.run(ingest(dry_run=args.dry_run))
