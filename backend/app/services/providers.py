import hashlib
import random
from typing import List, Dict, Any
from app.core.config import settings

class MockEmbeddings:
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            # deterministic pseudo-embedding based on hash
            h = hashlib.sha256(text.encode()).hexdigest()
            vec = []
            for i in range(0, 384, 2):
                val = int(h[i % len(h)], 16) / 15.0 - 0.5
                vec.append(val)
            embeddings.append(vec)
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]

class MockLLM:
    def generate(self, prompt: str, context: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Deterministic mock response
        if not context:
            return {
                "answer": "No hay información suficiente en los documentos indexados para responder con certeza.",
                "citations": [],
                "confidence": 0.1,
                "insufficient_evidence": True,
                "action": "abstain"
            }
        
        # Simulate generating answer with citations
        answer = f"Basado en los documentos proporcionados: {context[0]['content'][:200]}... "
        answer += "Para mayor detalle, consultar las citas referenciadas."
        
        citations = []
        for i, c in enumerate(context[:3]):
            citations.append({
                "chunk_id": c["chunk_id"],
                "document_id": c["document_id"],
                "document_name": c["document_name"],
                "page_number": c.get("page_number"),
                "section": c.get("section"),
                "snippet": c["content"][:150] + "..."
            })
        
        return {
            "answer": answer,
            "citations": citations,
            "confidence": 0.75,
            "insufficient_evidence": False,
            "action": "answer",
            "model_used": "mock/deterministic"
        }

class ProviderFactory:
    @staticmethod
    def get_embeddings():
        if settings.embed_provider == "mock":
            return MockEmbeddings()
        # Could add real providers here
        return MockEmbeddings()
    
    @staticmethod
    def get_llm():
        if settings.llm_provider == "mock":
            return MockLLM()
        return MockLLM()
