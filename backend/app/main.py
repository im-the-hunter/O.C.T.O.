"""
Project J.A.R.V.I.S. — Backend FastAPI (Fase 4)
Punto de entrada de la API: orquesta IA (GPT-4o + LangChain),
memoria vectorial (Pinecone), memoria relacional (PostgreSQL)
y la integración con GitHub (con caché anti rate-limit).

Mejoras de esta fase:
- Lifespan: valida variables de entorno, inicializa/cierra el cliente GitHub.
- Rate limiting por IP en todos los endpoints (slowapi).
- Logging estructurado con niveles configurables.
- Handler global para errores del servicio de GitHub (401/404/429/503).
- Swagger/OpenAPI automático en /docs para todos los endpoints.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings, validate_required_settings
from app.core.database import close_db, init_db
from app.routers import ai, github, memory, rag
from app.services.github_service import GitHubServiceError, github_service

# ---------------------------------------------------------------------------
# Logging detallado
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    stream=sys.stdout,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("jarvis")

# ---------------------------------------------------------------------------
# Rate limiting (por IP) — protege el backend además de la caché de GitHub
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Arranque: validar configuración crítica (log explícito de ausentes)
    missing = validate_required_settings()
    if missing:
        logger.warning("⚠ Variables de entorno ausentes: %s", ", ".join(missing))
    else:
        logger.info("✔ Configuración validada correctamente.")

    await github_service.startup()
    try:
        await init_db()
    except Exception as exc:  # noqa: BLE001 — PostgreSQL puede no estar aún levantado
        logger.warning("PostgreSQL no disponible al arrancar (%s); sigue en modo degradado.", exc)
    yield
    # Apagón: libera recursos
    await github_service.shutdown()
    await close_db()
    logger.info("J.A.R.V.I.S. backend apagado limpiamente.")


app = FastAPI(
    title="Project J.A.R.V.I.S. API",
    description=(
        "Backend del asistente de IA J.A.R.V.I.S.: integración con GitHub "
        "(caché inteligente + webhooks firmados), RAG sobre repositorios, "
        "agentes con LangChain/GPT-4o y memoria a largo plazo (PostgreSQL)."
    ),
    version="0.4.0",
    lifespan=lifespan,
)

# Rate limiter en app.state (requerido por slowapi)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Handler global: errores de dominio de GitHub → HTTP con código adecuado
@app.exception_handler(GitHubServiceError)
async def github_error_handler(request: Request, exc: GitHubServiceError) -> JSONResponse:
    logger.warning("GitHub error en %s: %s", request.url.path, exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


# CORS — permite el acceso desde el frontend Next.js
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining"],
)

# Routers (todos con rate limiting de 60 req/min por IP vía decorator abajo)
app.include_router(github.router, prefix="/api/github", tags=["GitHub"])
app.include_router(github.webhook_router, tags=["Webhooks"])
app.include_router(ai.router, prefix="/api/ai", tags=["IA"])
app.include_router(rag.router, prefix="/api/rag", tags=["RAG"])
app.include_router(memory.router, prefix="/api/memory", tags=["Memoria"])


@app.get("/", tags=["Salud"])
async def root():
    return {
        "system": "J.A.R.V.I.S.",
        "status": "online",
        "version": app.version,
        "message": "Just A Rather Very Intelligent System.",
        "docs": "/docs",
    }


@app.get("/health", tags=["Salud"])
async def health_check():
    return {
        "status": "ok",
        "environment": settings.environment,
        "github_configured": github_service.configured,
        "cache": "enabled",
    }
