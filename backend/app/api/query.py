from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.db import get_db
from app.core.tracing import tracer
from app.schemas.query import QueryRequest, QueryResponse, Citation
from app.services.rag_agent import rag_agent_service
import time

router = APIRouter()

@router.post("/query", response_model=QueryResponse)
async def query_documents(req: QueryRequest, db: AsyncSession = Depends(get_db)):
    start = time.time()
    with tracer.start_as_current_span("rag_query") as span:
        span.set_attribute("query.workspace", req.workspace_id)
        span.set_attribute("query.top_k", req.top_k)
        
        from app.services.providers import ProviderFactory
        embedder = ProviderFactory.get_embeddings()
        query_emb = embedder.embed_query(req.question)
        
        # Vector similarity search
        with tracer.start_as_current_span("pgvector_retrieval") as retr_span:
            sql = text("""
                SELECT c.id, c.document_id, c.content, c.page_number, c.section, c.workspace_id,
                       d.filename,
                       1 - (c.embedding <=> :query_emb) as score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.workspace_id = :workspace_id AND d.status = 'listo'
                ORDER BY c.embedding <=> :query_emb
                LIMIT :limit
            """)
            result = await db.execute(sql, {
                "query_emb": str(query_emb),
                "workspace_id": req.workspace_id,
                "limit": req.top_k
            })
            rows = result.fetchall()
            retr_span.set_attribute("fragments.retrieved", len(rows))
            span.set_attribute("fragments.retrieved", len(rows))
        
        if not rows:
            latency = (time.time() - start) * 1000
            return QueryResponse(
                answer="No hay documentos indexados o no se encontraron fragmentos relevantes.",
                citations=[],
                confidence=0.0,
                insufficient_evidence=True,
                action="abstain",
                model_used="none",
                latency_ms=latency,
                fragments_retrieved=0
            )
        
        # Build context
        context = []
        for r in rows:
            context.append({
                "chunk_id": str(r.id),
                "document_id": str(r.document_id),
                "document_name": r.filename,
                "content": r.content,
                "page_number": r.page_number,
                "section": r.section,
                "score": float(r.score)
            })
        
        # Generate answer with Pydantic AI (structured output validated)
        with tracer.start_as_current_span("llm_call") as llm_span:
            llm_result = rag_agent_service.generate_structured(req.question, context)
            llm_span.set_attribute("model.name", llm_result.get("model_used", "pydantic-ai"))
            llm_span.set_attribute("tokens.prompt", len(req.question) * 2)
            llm_span.set_attribute("tokens.completion", len(llm_result.get("answer", "")) * 2)
            span.set_attribute("model.name", llm_result.get("model_used", "pydantic-ai"))
        
        latency = (time.time() - start) * 1000
        span.set_attribute("latency.ms", latency)
        
        citations = []
        for c in llm_result.get("citations", []):
            chunk_id = c.get("chunk_id")
            # attach score if found
            score = 0.5
            for ctx in context:
                if str(ctx["chunk_id"]) == str(chunk_id):
                    score = ctx["score"]
                    break
            citations.append(Citation(
                chunk_id=chunk_id,
                document_id=c["document_id"],
                document_name=c["document_name"],
                page_number=c.get("page_number"),
                section=c.get("section"),
                snippet=c.get("snippet", "")[:200] + "...",
                score=score
            ))
        
        return QueryResponse(
            answer=llm_result["answer"],
            citations=citations,
            confidence=llm_result.get("confidence", 0.5),
            insufficient_evidence=llm_result.get("insufficient_evidence", False),
            action=llm_result.get("action", "answer"),
            model_used=llm_result.get("model_used", "pydantic-ai"),
            latency_ms=round(latency, 2),
            fragments_retrieved=len(rows)
        )
