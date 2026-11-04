from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from opentelemetry import trace
from app.core.config import settings
from app.core.db import get_db
from app.core.tracing import tracer
from app.schemas.query import QueryRequest, QueryResponse, Citation
from app.services.rag_agent import rag_agent_service
import time

router = APIRouter()

ABSTAIN_NO_EVIDENCE = (
    "No he encontrado evidencia suficiente en los documentos indexados para responder. "
    "Reformula la pregunta o sube el documento que contenga esa información."
)


@router.post("/query", response_model=QueryResponse)
async def query_documents(req: QueryRequest, db: AsyncSession = Depends(get_db)):
    start = time.time()
    with tracer.start_as_current_span("rag_query") as span:
        span.set_attribute("query.workspace", req.workspace_id)
        span.set_attribute("query.top_k", req.top_k)
        span.set_attribute("query.question_length", len(req.question))

        from app.services.providers import ProviderFactory

        embedder = ProviderFactory.get_embeddings()
        query_emb = embedder.embed_query(req.question)

        # Vector similarity search (cosine distance -> similarity)
        with tracer.start_as_current_span("pgvector_retrieval") as retr_span:
            sql = text(
                """
                SELECT c.id, c.document_id, c.content, c.page_number, c.section, c.workspace_id,
                       d.filename,
                       1 - (c.embedding <=> CAST(:query_emb AS vector)) as score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.workspace_id = :workspace_id
                  AND d.workspace_id = :workspace_id
                  AND d.status = 'listo'
                ORDER BY c.embedding <=> CAST(:query_emb AS vector)
                LIMIT :limit
                """
            )
            result = await db.execute(
                sql,
                {
                    "query_emb": str(query_emb),
                    "workspace_id": req.workspace_id,
                    "limit": req.top_k,
                },
            )
            rows = result.fetchall()
            retr_span.set_attribute("fragments.retrieved", len(rows))
            span.set_attribute("fragments.retrieved", len(rows))

        # Evidence gating: only fragments above the similarity floor count.
        evidence = [r for r in rows if r.score is not None and float(r.score) >= settings.min_evidence_score]
        span.set_attribute("fragments.used", len(evidence))
        span.set_attribute("evidence.min_score", settings.min_evidence_score)

        trace_id = format(span.get_span_context().trace_id, "032x")

        if not evidence:
            latency = (time.time() - start) * 1000
            span.set_attribute("answer.action", "abstain")
            span.set_attribute("latency.ms", latency)
            return QueryResponse(
                answer=ABSTAIN_NO_EVIDENCE,
                citations=[],
                confidence=0.0,
                insufficient_evidence=True,
                action="abstain",
                model_used="evidence-gate",
                latency_ms=round(latency, 2),
                fragments_retrieved=len(rows),
                trace_id=trace_id,
            )

        context = [
            {
                "chunk_id": str(r.id),
                "document_id": str(r.document_id),
                "document_name": r.filename,
                "content": r.content,
                "page_number": r.page_number,
                "section": r.section,
                "score": float(r.score),
            }
            for r in evidence
        ]

        with tracer.start_as_current_span("llm_call") as llm_span:
            llm_result = rag_agent_service.generate_structured(req.question, context)
            llm_span.set_attribute("model.name", llm_result.get("model_used", "pydantic-ai"))
            llm_span.set_attribute("tokens.prompt", len(req.question) * 2)
            llm_span.set_attribute("tokens.completion", len(llm_result.get("answer", "")) * 2)
            span.set_attribute("model.name", llm_result.get("model_used", "pydantic-ai"))

        latency = (time.time() - start) * 1000
        span.set_attribute("latency.ms", latency)
        span.set_attribute("answer.action", llm_result.get("action", "answer"))
        span.set_attribute("answer.insufficient_evidence", bool(llm_result.get("insufficient_evidence")))

        # Citations are only valid if they point to a retrieved chunk.
        by_id = {ctx["chunk_id"]: ctx for ctx in context}
        citations = []
        for c in llm_result.get("citations", []):
            ctx = by_id.get(str(c.get("chunk_id")))
            if not ctx:
                continue
            citations.append(
                Citation(
                    chunk_id=ctx["chunk_id"],
                    document_id=ctx["document_id"],
                    document_name=ctx["document_name"],
                    page_number=ctx.get("page_number"),
                    section=ctx.get("section"),
                    snippet=ctx["content"][:200],
                    score=ctx["score"],
                )
            )

        return QueryResponse(
            answer=llm_result["answer"],
            citations=citations,
            confidence=llm_result.get("confidence", 0.5),
            insufficient_evidence=llm_result.get("insufficient_evidence", False),
            action=llm_result.get("action", "answer"),
            model_used=llm_result.get("model_used", "pydantic-ai"),
            latency_ms=round(latency, 2),
            fragments_retrieved=len(rows),
            trace_id=trace_id,
        )
