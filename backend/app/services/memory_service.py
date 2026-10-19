"""
Servicio de memoria a largo plazo sobre PostgreSQL (SQLAlchemy async).
Almacena conversaciones y recuerdos clave/valor del usuario.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import ConversationMessage, LongTermMemory


class MemoryService:
    async def add_message(
        self, db: AsyncSession, session_id: str, role: str, content: str
    ) -> None:
        db.add(
            ConversationMessage(
                session_id=session_id, role=role, content=content, created_at=datetime.now(timezone.utc)
            )
        )
        await db.flush()

    async def get_conversation(self, db: AsyncSession, session_id: str) -> list[dict]:
        result = await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.created_at.asc())
        )
        return [
            {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
            for m in result.scalars().all()
        ]

    async def store(
        self, db: AsyncSession, key: str, value: str, category: str = "general"
    ) -> dict:
        record = LongTermMemory(
            key=key, value=value, category=category, created_at=datetime.now(timezone.utc)
        )
        db.add(record)
        await db.flush()
        return {"id": record.id, "key": key}

    async def search(self, db: AsyncSession, query: str) -> list[dict]:
        result = await db.execute(
            select(LongTermMemory).where(LongTermMemory.value.ilike(f"%{query}%"))
        )
        return [
            {"id": r.id, "key": r.key, "value": r.value, "category": r.category}
            for r in result.scalars().all()
        ]
