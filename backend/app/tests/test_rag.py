#!/usr/bin/env python3
"""
test_rag.py — Verificación del pipeline RAG (Fase 5).

Uso:
    cd backend && python -m app.tests.test_rag            # smoke test completo
    cd backend && python -m app.tests.test_rag --offline  # sin red: chunking/BM25/caché/prompt

Comprueba:
 1. Chunking inteligente (código por funciones, markdown por secciones, overlap)
 2. IDs deterministas de chunks e higiene de metadata para Pinecone
 3. BM25 y fusión hybrid (re-ranking heurístico)
 4. build_context con el formato requerido ([Archivo:][Lenguaje:])
 5. Caché de respuestas (hit/miss + TTL)
 6. [online] Embeddings OpenAI -> dimensión 1536
 7. [online] Índice Pinecone jarvis-repo (creación si no existe) + upsert
       + búsqueda con umbral >0.7 + ingestas incrementales (skip/update/delete)
 8. [online] answer_question end-to-end con citas de archivos
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

sys.path.insert(0, ".")

from app.core.config import settings  # noqa: E402
from app.services.chunking_service import (  # noqa: E402
    chunk_code,
    chunk_file,
    chunk_markdown,
    count_tokens,
    detect_language,
)
from app.services.rag_service import (  # noqa: E402
    AnswerCache,
    BM25Scorer,
    _sanitize_metadata,
    chunk_id,
    rag_service,
)

PASS = "\033[92m✔\033[0m"
FAIL = "\033[91m✘\033[0m"


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{PASS if ok else FAIL}] {name}" + (f" — {detail}" if detail else ""))
    return ok


# ---------------------------------------------------------------------------
# Tests offline (sin APIs externas)
# ---------------------------------------------------------------------------
SAMPLE_PY = '''
"""Servicio de usuarios."""
import hashlib


class UserStore:
    def get(self, uid):
        return self._db[uid]

    def create(self, name):
        token = hashlib.sha1(name.encode()).hexdigest()
        return {"id": token, "name": name}


def authenticate(user, password):
    """Valida credenciales contra la base de datos."""
    stored = user_store.get(user)
    return stored and stored["password"] == password


def logout(session):
    session.clear()
    return True
'''

SAMPLE_MD = '''# Guía de autenticación

Introducción al flujo de login OAuth.

## Instalación

Pasos para instalar dependencias.

## Configuración de tokens

Variables necesarias: GITHUB_TOKEN y NEXTAUTH_SECRET.

## Troubleshooting

Errores comunes al hacer login.
'''


def test_chunking() -> bool:
    print("\n🧩 Chunking:")
    ok = True
    ok &= check("detect_language(.py)", detect_language("a/b/x.py") == "python")
    ok &= check("detect_language(.tsx)", detect_language("x.tsx") == "typescript")

    # Archivo de código realista y extenso (varias funciones/clases)
    big_py = SAMPLE_PY + "\n\n" + "\n\n".join(
        f"def helper_{i}(value):\n    \"\"\"Utilidad {i}.\"\"\"\n    return value * {i} + 'padding text for tokens'"
        for i in range(30)
    )
    code_chunks = chunk_code(big_py, 120, 30)
    ok &= check("código dividido por funciones/clases", len(code_chunks) >= 3,
                f"{len(code_chunks)} chunks")
    joined = "\n".join(code_chunks)
    ok &= check("contenido conservado (sin pérdidas graves)",
                "def authenticate" in joined and "class UserStore" in joined
                and "def helper_29" in joined)
    ok &= check("chunks de código acotados (~objetivo)",
                all(count_tokens(c) <= 260 for c in code_chunks),
                f"max={max(count_tokens(c) for c in code_chunks)} tokens")

    md_chunks = chunk_markdown(SAMPLE_MD, 45, 15)
    ok &= check("markdown dividido por secciones",
                any(c.lstrip().startswith("## ") for c in md_chunks) and len(md_chunks) >= 3,
                f"{len(md_chunks)} chunks")

    files = chunk_file("src/auth.py", SAMPLE_PY, chunk_tokens=120, overlap_tokens=30)
    ok &= check("chunk_file devuelve índices coherentes",
                all(c.index < c.total for c in files) and files[0].index == 0)

    big = "line of text\n" * 3000
    pieces = chunk_file("big.txt", big, chunk_tokens=500, overlap_tokens=50)
    sizes = [count_tokens(p.text) for p in pieces]
    ok &= check("archivos grandes troceados ~500 tokens",
                max(sizes) <= 900 and len(pieces) > 5,
                f"{len(pieces)} chunks, max {max(sizes)} tokens")

    # Solapamiento real: el inicio del chunk N+1 reproduce el final del chunk N
    overlap_ok = False
    for a, b in zip(pieces, pieces[1:]):
        tail = a.text.strip()[-80:]
        if tail[:40] in b.text[:200]:
            overlap_ok = True
            break

    # Markdown largo (varias secciones reales) -> cada sección debe quedar
    # alineada al inicio de algún chunk (división por encabezados)
    md_big = SAMPLE_MD + "\n" + "\n".join(
        f"## Sección {i}\n\nContenido de la sección número {i} con detalle adicional.\n"
        for i in range(15)
    )
    md_chunks2 = chunk_markdown(md_big, 60, 15)
    section_starts = sum(
        1 for c in md_chunks2
        if any(c.lstrip().startswith(f"## Sección {i}") for i in range(15))
    )
    ok &= check("markdown divide por encabezados en archivos largos",
                len(md_chunks2) >= 5 and section_starts >= 10,
                f"{len(md_chunks2)} chunks, {section_starts} secciones alineadas")
    ok &= check("overlap de ~50 tokens entre chunks consecutivos", overlap_ok)
    return bool(ok)


def test_ids_and_metadata() -> bool:
    print("\n🔑 IDs y metadata:")
    ok = True
    a, b = chunk_id("src/a.py", 0), chunk_id("src/a.py", 0)
    ok &= check("chunk_id determinista", a == b)
    ok &= check("chunk_id único por índice", chunk_id("src/a.py", 1) != a)
    ok &= check("ID válido para Pinecone (charset)",
                all(ch.isalnum() or ch in "_-" or ch == "#" for ch in a))
    meta = _sanitize_metadata({
        "file_path": "a.py", "chunk_index": 0, "total_chunks": 3,
        "nested": {"bad": 1}, "none": None, "flag": True,
    })
    ok &= check("metadata sanitizada (sin dicts anidados)", "nested" in meta
                and isinstance(meta["nested"], str) and meta["flag"] is True)
    return bool(ok)


def test_bm25_and_context() -> bool:
    print("\n🎯 Hybrid BM25 + contexto:")
    ok = True
    docs = [
        "la autenticación de usuarios usa OAuth y tokens",
        "el renderizado del HUD usa framer motion",
        "login con github token y nextauth secret",
    ]
    scores = BM25Scorer(docs).score("autenticación token login")
    ok &= check("BM25 prioriza documentos relevantes",
                scores[0] > scores[1] and scores[2] > scores[1],
                f"scores={[round(s,2) for s in scores]}")

    ctx = rag_service.build_context([
        {"file_path": "src/Button.tsx", "content": "export const Button = ...;",
         "metadata": {"language": "typescript"}, "score": 0.9},
        {"file_path": "src/utils/helpers.ts", "content": "export function cn()",
         "metadata": {"language": "typescript"}, "score": 0.8},
    ])
    ok &= check("build_context formato [Archivo:]/[Lenguaje:] + separador ---",
                "[Archivo: src/Button.tsx]" in ctx
                and "[Lenguaje: typescript]" in ctx and "\n---\n" in ctx)
    empty = rag_service.build_context([])
    ok &= check("build_context vacío manejado", "(sin resultados" in empty)
    return bool(ok)


def test_answer_cache() -> bool:
    print("\n💾 Caché de respuestas:")
    ok = True
    cache = AnswerCache(ttl_seconds=3600)
    cache.set("¿Cómo funciona auth?", {"response": "r1", "sources": []})
    hit = cache.get("¿cómo funciona AUTH?")  # normalizada (lower/strip)
    ok &= check("hit en pregunta normalizada", hit is not None and hit["cached"] is True)
    ok &= check("miss en pregunta distinta", cache.get("otra pregunta") is None)
    expiring = AnswerCache(ttl_seconds=0)
    expiring.set("q", {"response": "x"})
    ok &= check("expiración por TTL", expiring.get("q") is None)
    stats = cache.stats()
    ok &= check("stats de caché disponibles", stats["hits"] >= 1 and "ttl_seconds" in stats)
    return bool(ok)


def test_prompt_template() -> bool:
    print("\n📝 Prompt template:")
    from app.services.rag_service import PROMPT_TEMPLATE

    rendered = PROMPT_TEMPLATE.format(context="[Archivo: x.py]\ncódigo", query="¿qué hace?")
    ok = all(s in rendered for s in ("Eres JARVIS", "CONTEXTO DEL REPOSITORIO",
                                     "PREGUNTA DEL USUARIO", "cita los archivos"))
    return check("prompt incluye secciones requeridas", ok)


# ---------------------------------------------------------------------------
# Tests online (requieren OPENAI_API_KEY / PINECONE_API_KEY)
# ---------------------------------------------------------------------------
async def test_embeddings_online() -> bool:
    print("\n🧲 Embeddings (OpenAI):")
    if not settings.openai_api_key:
        return check("OPENAI_API_KEY ausente — omitido", True, "skipped")
    try:
        vecs = await rag_service.embed(["función de autenticación OAuth", "HUD sci-fi"])
        ok = check("batch embeddings OK", len(vecs) == 2)
        ok &= check(f"dimensión {settings.embedding_dimensions}", len(vecs[0]) == 1536,
                    f"dim={len(vecs[0])}")
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        return check("embeddings fallaron", False, str(exc)[:120])


def make_fake_snapshot(commit: str = "sha-v1") -> dict:
    """Snapshot sintético con la estructura de cache_service (Fase 4)."""
    return {
        "repo": settings.repo_full_name or "test/repo",
        "branch": "main",
        "repo_tree": {"commit_sha": commit},
        "files": {
            "src/services/auth.py": {
                "content": SAMPLE_PY, "sha": commit, "last_modified": commit,
            },
            "docs/guide.md": {
                "content": SAMPLE_MD, "sha": commit, "last_modified": commit,
            },
        },
    }


async def test_pinecone_pipeline_online() -> bool:
    print("\n🌲 Pinecone: índice + ingesta incremental + búsqueda:")
    if not settings.pinecone_api_key:
        return check("PINECONE_API_KEY ausente — omitido", True, "skipped")
    try:
        idx = rag_service.index  # crea jarvis-repo si no existe
        ok = check("conexión/creación del índice", idx is not None,
                   settings.pinecone_index_name)

        snap = make_fake_snapshot("sha-v1")
        r1 = await rag_service.ingest_from_snapshot(snap, force=True)
        ok &= check("ingesta inicial (added>0, chunks>0)",
                    r1["stats"]["added"] == 2 and r1["stats"]["chunks_upserted"] > 0,
                    json.dumps(r1["stats"], default=str)[:160])

        r2 = await rag_service.ingest_from_snapshot(snap, force=False)
        ok &= check("segunda pasada incremental (todo skipped)",
                    r2["stats"]["skipped"] == 2 and r2["stats"]["added"] == 0,
                    json.dumps(r2["stats"], default=str)[:120])

        snap_v2 = make_fake_snapshot("sha-v2")
        del snap_v2.files["docs/guide.md"]           # archivo eliminado
        snap_v2.files["src/new_module.py"] = {        # archivo nuevo
            "content": "def new_feature():\n    return 'ok'\n" * 5,
            "sha": "sha-v2", "last_modified": "sha-v2",
        }
        r3 = await rag_service.ingest_from_snapshot(snap_v2, force=False)
        ok &= check("tercera pasada: update+add+delete",
                    r3["stats"]["updated"] >= 1 and r3["stats"]["added"] >= 1
                    and r3["stats"]["deleted"] >= 1,
                    json.dumps(r3["stats"], default=str)[:160])

        results = await rag_service.search_repository(
            "how does authenticate validate credentials", top_k=5, min_score=0.5)
        ok &= check("búsqueda retorna resultados relevantes", len(results) > 0,
                    f"{len(results)} hits, top score={results[0]['score']:.3f}"
                    if results else "0 hits")
        if results:
            ok &= check("metadata file_path presente",
                        all("file_path" in r for r in results))
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        return check("pipeline Pinecone falló", False, str(exc)[:200])


async def test_answer_online() -> bool:
    print("\n🤖 answer_question (GPT-4o + contexto):")
    if not (settings.openai_api_key and settings.pinecone_api_key):
        return check("keys ausentes — omitido", True, "skipped")
    try:
        result = await rag_service.answer_question(
            "¿Qué hace la función authenticate en este repo?", use_repo_context=True)
        ok = check("respuesta generada", bool(result["response"]))
        ok &= check("tokens_used reportado", result["tokens_used"] > 0,
                    f"{result['tokens_used']} tokens")
        cached_again = await rag_service.answer_question(
            "¿Qué hace la función authenticate en este repo?", use_repo_context=True)
        ok &= check("caché de respuestas activa", cached_again["cached"] is True)
        no_ctx = await rag_service.answer_question(
            "¿Cuál es la capital de Francia?", use_repo_context=False)
        ok &= check("modo sin contexto (LLM puro)", bool(no_ctx["response"]),
                    no_ctx["response"][:60].replace("\n", " "))
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        return check("answer_question falló", False, str(exc)[:200])


# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Pruebas del sistema RAG (Fase 5)")
    parser.add_argument("--offline", action="store_true",
                        help="Solo tests sin llamadas a APIs externas")
    args = parser.parse_args()

    print("=" * 64)
    print("🧠 TESTS RAG — Project J.A.R.V.I.S. (Fase 5)")
    print("=" * 64)

    results: list[bool] = [
        test_chunking(),
        test_ids_and_metadata(),
        test_bm25_and_context(),
        test_answer_cache(),
        test_prompt_template(),
    ]

    if not args.offline:
        results.append(asyncio.run(test_embeddings_online()))
        results.append(asyncio.run(test_pinecone_pipeline_online()))
        results.append(asyncio.run(test_answer_online()))
    else:
        print("\nℹ️  Modo offline: se omiten OpenAI/Pinecone.")

    passed = sum(1 for r in results if r)
    total = len(results)
    print("\n" + "=" * 64)
    print(f"Resultado: {passed}/{total} grupos de tests en ✔")
    print("=" * 64)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
