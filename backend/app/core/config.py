"""
Configuración central del backend mediante pydantic-settings.
Lee variables desde backend/.env (ver .env.example en la raíz).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Entorno / servidor ---
    environment: str = "development"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    # --- OpenAI ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    # --- Pinecone (memoria vectorial / RAG) ---
    pinecone_api_key: str = ""
    pinecone_environment: str = ""
    pinecone_index_name: str = "jarvis-repo"
    embedding_dimensions: int = 1536

    # --- RAG (Fase 5) ---
    rag_chunk_tokens: int = 500          # tamaño objetivo de chunk en tokens
    rag_chunk_overlap_tokens: int = 50   # solapamiento entre chunks
    rag_min_score: float = 0.70          # umbral mínimo de similitud coseno
    rag_top_k_default: int = 5
    rag_answer_cache_ttl: int = 3600     # caché de respuestas (1 hora)
    # Re-ranking opcional con Cohere (si no hay API key se usa re-ranking heurístico)
    cohere_api_key: str = ""
    cohere_rerank_model: str = "rerank-english-v3.0"

    # --- PostgreSQL (memoria a largo plazo) ---
    database_url: str = "postgresql://jarvis:jarvis_password@localhost:5432/jarvis_db"
    database_url_async: str = (
        "postgresql+asyncpg://jarvis:jarvis_password@localhost:5432/jarvis_db"
    )

    # --- GitHub ---
    github_token: str = ""
    github_repo_owner: str = ""
    github_repo_name: str = ""
    github_branch: str = "main"
    # Secret para validar la firma (X-Hub-Signature-256) de los webhooks
    github_webhook_secret: str = ""

    # --- Caché GitHub ---
    cache_dir: str = ".cache/github"
    cache_ttl_seconds: int = 3600  # 1 hora por defecto
    max_file_size_bytes: int = 1_048_576  # 1 MB por archivo
    redis_url: str = ""  # opcional: redis://localhost:6379/0

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def repo_full_name(self) -> str:
        return f"{self.github_repo_owner}/{self.github_repo_name}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def validate_required_settings() -> list[str]:
    """Devuelve la lista de variables de entorno críticas ausentes.

    No lanza excepción para permitir arrancar el servidor en modo degradado
    (los endpoints de GitHub responderán 503 con un mensaje claro).
    """
    required = {
        "GITHUB_TOKEN": settings.github_token,
        "GITHUB_REPO_OWNER": settings.github_repo_owner,
        "GITHUB_REPO_NAME": settings.github_repo_name,
        "OPENAI_API_KEY": settings.openai_api_key,
        "DATABASE_URL": settings.database_url,
    }
    return [name for name, value in required.items() if not value]
