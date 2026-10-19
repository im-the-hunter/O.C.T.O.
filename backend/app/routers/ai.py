"""Endpoints de IA: chat con agente (LangChain + GPT-4o) y RAG sobre el repo."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.agent_service import AgentService
from app.services.rag_service import RAGService

router = APIRouter()
agent_service = AgentService()
rag_service = RAGService()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Mensaje del usuario")
    session_id: str = Field("default", description="Hilo de conversación")
    use_rag: bool = Field(True, description="Contextualizar con el repo vectorizado")


class ChatResponse(BaseModel):
    reply: str
    sources: list[str] = []
    session_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Conversación principal con J.A.R.V.I.S. (agente + RAG opcional)."""
    try:
        context = ""
        sources: list[str] = []
        if request.use_rag:
            docs = await rag_service.retrieve(request.message, k=5)
            context = "\n\n".join(d["content"] for d in docs)
            sources = [d["metadata"].get("source", "") for d in docs]

        reply = await agent_service.run(
            user_message=request.message,
            context=context,
            session_id=request.session_id,
        )
        return ChatResponse(reply=reply, sources=sources, session_id=request.session_id)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/models")
async def list_models():
    """Modelos disponibles configurados en el sistema."""
    return {"chat": "gpt-4o", "embeddings": "text-embedding-3-small"}
