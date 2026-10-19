"""Endpoints de memoria a largo plazo (PostgreSQL): conversaciones y hechos."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.services.memory_service import MemoryService

router = APIRouter()
memory_service = MemoryService()


class MemoryStoreRequest(BaseModel):
    key: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)
    category: str = Field("general", description="general | preferencia | hecho")


@router.get("/conversations/{session_id}")
async def get_conversation(session_id: str, db: AsyncSession = Depends(get_session)):
    """Histórico de mensajes de una sesión."""
    messages = await memory_service.get_conversation(db, session_id)
    return {"session_id": session_id, "messages": messages}


@router.post("/store")
async def store_memory(payload: MemoryStoreRequest, db: AsyncSession = Depends(get_session)):
    """Guarda un recuerdo de largo plazo clave/valor."""
    record = await memory_service.store(db, payload.key, payload.value, payload.category)
    return {"status": "stored", "id": record["id"]}


@router.get("/search")
async def search_memory(q: str, db: AsyncSession = Depends(get_session)):
    """Búsqueda simple de recuerdos por texto."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Consulta vacía")
    results = await memory_service.search(db, q)
    return {"query": q, "results": results}
