"""
Conexión a PostgreSQL (memoria a largo plazo) con SQLAlchemy async.
Expone el motor, la sesión asíncrona y helpers de ciclo de vida.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.database_url_async,
    echo=settings.environment == "development",
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos ORM."""

    pass


async def init_db() -> None:
    """Crea las tablas si no existen (en producción usar Alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Cierra el pool de conexiones."""
    await engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia de FastAPI que inyecta una sesión de BD."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
