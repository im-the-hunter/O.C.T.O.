"""
Servicio de agente conversacional con LangChain + GPT-4o.
Combina: prompt de sistema de J.A.R.V.I.S. + contexto RAG + historial de sesión.
"""
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings

JARVIS_SYSTEM_PROMPT = """Eres J.A.R.V.I.S., el asistente de IA personal del usuario.
Personalidad: cortés, preciso, ligeramente ingenioso, siempre se dirige al usuario
como "señor". Respondes en español salvo que se te pida otro idioma.

Tienes acceso a contexto recuperado del repositorio de GitHub del usuario.
Usa ese contexto para responder sobre el código; cita archivos cuando sea útil.
Si la información no está en el contexto, dilo honestamente.

CONTEXTO DEL REPOSITORIO:
{context}
"""


class AgentService:
    def __init__(self) -> None:
        self.llm = ChatOpenAI(
            model=settings.openai_model,          # gpt-4o
            temperature=0.7,
            api_key=settings.openai_api_key,
        )
        # Historial simple en memoria por sesión (la persistencia real va a PostgreSQL)
        self._histories: dict[str, list] = {}

    async def run(self, user_message: str, context: str = "", session_id: str = "default") -> str:
        history = self._histories.setdefault(session_id, [])

        messages = [
            SystemMessage(content=JARVIS_SYSTEM_PROMPT.format(context=context or "(sin contexto)")),
            *history[-10:],  # últimos 10 mensajes como memoria de corto plazo
            HumanMessage(content=user_message),
        ]

        response = await self.llm.ainvoke(messages)

        history.append(HumanMessage(content=user_message))
        history.append(response)
        return response.content
