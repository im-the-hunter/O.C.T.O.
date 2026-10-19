"""
Project J.A.R.V.I.S. — Backend FastAPI
Punto de entrada de la API: orquesta IA (GPT-4o + LangChain),
memoria vectorial (Pinecone), memoria relacional (PostgreSQL)
y la integración con GitHub.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import close_db, init_db
from app.routers import ai, github, memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Arranque: inicializa conexiones (PostgreSQL, Pinecone)
    await init_db()
    yield
    # Apagón: libera recursos
    await close_db()


app = FastAPI(
    title="Project J.A.R.V.I.S. API",
    description=(
        "Backend del asistente de IA J.A.R.V.I.S.: RAG sobre repositorios "
        "de GitHub, agentes con LangChain/GPT-4o y memoria a largo plazo."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — permite el acceso desde el frontend Next.js
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(github.router, prefix="/api/github", tags=["GitHub"])
app.include_router(ai.router, prefix="/api/ai", tags=["IA"])
app.include_router(memory.router, prefix="/api/memory", tags=["Memoria"])


@app.get("/", tags=["Salud"])
async def root():
    return {
        "system": "J.A.R.V.I.S.",
        "status": "online",
        "message": "Just A Rather Very Intelligent System.",
    }


@app.get("/health", tags=["Salud"])
async def health_check():
    return {"status": "ok", "environment": settings.environment}
