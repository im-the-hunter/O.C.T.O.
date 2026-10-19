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
    pinecone_index_name: str = "jarvis-repo-index"

    # --- PostgreSQL (memoria a largo plazo) ---
    database_url: str = "postgresql://jarvis:jarvis_password@localhost:5432/jarvis_db"
    database_url_async: str = (
        "postgresql+asyncpg://jarvis:jarvis_password@localhost:5432/jarvis_db"
    )

    # --- GitHub ---
    github_token: str = ""
    github_repo_owner: str = ""
    github_repo_name: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
