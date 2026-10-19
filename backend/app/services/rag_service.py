"""
Servicio RAG (Retrieval-Augmented Generation):
- Genera embeddings con OpenAI (text-embedding-3-small).
- Almacena y consulta vectores en Pinecone.
"""
from typing import Any

from openai import AsyncOpenAI
from pinecone import Pinecone, ServerlessIndex

from app.core.config import settings


class RAGService:
    def __init__(self) -> None:
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self._pc = Pinecone(api_key=settings.pinecone_api_key)
        self._index: ServerlessIndex | None = None

    @property
    def index(self) -> ServerlessIndex:
        if self._index is None:
            self._index = self._pc.Index(settings.pinecone_index_name)
        return self._index

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Genera embeddings para una lista de textos."""
        response = await self._openai.embeddings.create(
            model=settings.openai_embedding_model, input=texts
        )
        return [item.embedding for item in response.data]

    async def upsert_documents(self, docs: list[dict]) -> int:
        """
        Inserta/actualiza documentos vectorizados.
        Cada doc: {"id": str, "content": str, "metadata": dict}
        """
        vectors = await self.embed([d["content"] for d in docs])
        payload = [
            {"id": d["id"], "values": v, "metadata": {**d.get("metadata", {}), "text": d["content"]}}
            for d, v in zip(docs, vectors)
        ]
        # Upsert por lotes de 100 (límite recomendado de Pinecone)
        total = 0
        for i in range(0, len(payload), 100):
            batch = payload[i : i + 100]
            self.index.upsert(vectors=batch)
            total += len(batch)
        return total

    async def retrieve(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Búsqueda semántica: devuelve los k fragmentos más relevantes."""
        query_vector = (await self.embed([query]))[0]
        results = self.index.query(vector=query_vector, top_k=k, include_metadata=True)
        return [
            {
                "id": match["id"],
                "score": match["score"],
                "content": match["metadata"].get("text", ""),
                "metadata": match.get("metadata", {}),
            }
            for match in results.get("matches", [])
        ]
