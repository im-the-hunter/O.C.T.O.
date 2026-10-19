#!/usr/bin/env python3
"""
Script de inicialización de la base de datos PostgreSQL
(memoria a largo plazo de J.A.R.V.I.S.).

Crea las tablas definidas en los modelos ORM (con pgvector si está disponible).

Uso:
    cd backend && python ../scripts/setup_db.py [--drop]
"""
import argparse
import asyncio
import os
import sys

# Permite ejecutar el script desde backend/ sin instalar el paquete
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy.ext.asyncio import AsyncEngine  # noqa: E402

from app.core.database import Base, engine  # noqa: E402
import app.models.memory  # noqa: E402,F401 (registra los modelos en metadata)


async def setup(drop: bool = False) -> None:
    print("🛠️  Inicializando base de datos PostgreSQL de J.A.R.V.I.S....")
    async with engine.begin() as conn:
        if drop:
            print("⚠️  Eliminando todas las tablas existentes...")
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tablas creadas: conversation_messages, long_term_memories")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inicializa la BD relacional de J.A.R.V.I.S.")
    parser.add_argument("--drop", action="store_true", help="Elimina y recrea las tablas")
    args = parser.parse_args()
    asyncio.run(setup(drop=args.drop))
