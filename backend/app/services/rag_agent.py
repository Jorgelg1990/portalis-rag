from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic import BaseModel, Field
from typing import List, Optional
from app.core.config import settings

class CitationOut(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    page_number: Optional[int] = None
    section: Optional[str] = None
    snippet: str

class RAGStructuredOutput(BaseModel):
    answer: str = Field(description="Respuesta concisa basada únicamente en los fragmentos recuperados")
    citations: List[CitationOut] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    insufficient_evidence: bool
    action: str = Field(description="answer | abstain | ask_clarification")

class RAGAgentService:
    def __init__(self):
        self.use_mock = settings.llm_provider == "mock" or settings.env == "dev"
    
    def get_agent(self):
        if self.use_mock:
            # TestModel para modo sin llaves / determinista
            return Agent(TestModel(), result_type=RAGStructuredOutput)
        # Con claves reales usar LiteLLM/Gemini
        model = settings.litellm_model or "gemini/gemini-1.5-flash"
        return Agent(model, result_type=RAGStructuredOutput)
    
    def generate_structured(self, question: str, context: List[dict]):
        agent = self.get_agent()
        if not context:
            # Forzar respuesta abstención sin llamar agente
            return {
                "answer": "No hay información suficiente en los documentos indexados para responder con certeza.",
                "citations": [],
                "confidence": 0.1,
                "insufficient_evidence": True,
                "action": "abstain"
            }
        
        # Construir prompt con contexto limitado
        ctx_text = "\n\n".join([
            f"[DOC:{c['document_name']} p.{c.get('page_number') or '-'}]\n{c['content'][:400]}"
            for c in context[:4]
        ])
        
        prompt = f"""Responde ÚNICAMENTE con información presente en los fragmentos.
Si no hay evidencia suficiente, usa action='abstain' o 'ask_clarification' con insufficient_evidence=true.
No inventes información. Sé conciso y cita usando los fragmentos provistos.

Pregunta: {question}

Fragmentos recuperados:
{ctx_text}
"""
        try:
            result = agent.run_sync(prompt)
            data = result.data
            # Convertir a dict compatible con nuestra API
            return {
                "answer": data.answer,
                "citations": [c.model_dump() for c in data.citations],
                "confidence": data.confidence,
                "insufficient_evidence": data.insufficient_evidence,
                "action": data.action,
                "model_used": "pydantic-ai" if not self.use_mock else "pydantic-ai/testmodel"
            }
        except Exception as e:
            # Fallback seguro
            return {
                "answer": f"Error al generar respuesta estructurada: {str(e)[:100]}",
                "citations": [],
                "confidence": 0.0,
                "insufficient_evidence": True,
                "action": "abstain",
                "model_used": "pydantic-ai/error"
            }

rag_agent_service = RAGAgentService()
