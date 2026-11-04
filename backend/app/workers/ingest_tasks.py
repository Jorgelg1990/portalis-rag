from app.workers.celery_app import celery_app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.document import Document, IngestStatus
from app.models.chunk import Chunk
from app.services.parser import parse_document
from app.services.chunking import chunk_blocks
from app.services.providers import ProviderFactory
from app.core.tracing import tracer
from opentelemetry import trace

# Simple sync DB for worker
engine = create_engine(settings.sync_database_url)
SessionLocal = sessionmaker(bind=engine)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_document(self, document_id: str, file_path: str, workspace_id: str):
    with tracer.start_as_current_span("ingest_document") as span:
        span.set_attribute("document.id", document_id)
        span.set_attribute("workspace.id", workspace_id)
        span.set_attribute("parser.name", settings.parser)

        db = SessionLocal()
        doc = None
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if not doc:
                return {"error": "document not found"}

            doc.status = IngestStatus.PROCESANDO
            doc.error_message = None
            db.commit()

            blocks = parse_document(file_path, parser=settings.parser)
            span.set_attribute("blocks.count", len(blocks))

            chunks = chunk_blocks(blocks, max_chars=settings.chunk_max_chars)
            if not chunks:
                raise ValueError("El documento no produjo fragmentos de texto")

            embedder = ProviderFactory.get_embeddings()
            embeddings = embedder.embed_texts([c["content"] for c in chunks])
            span.set_attribute("chunks.count", len(chunks))
            span.set_attribute("embedding.provider", settings.embed_provider)

            # Idempotencia: un reintento no debe duplicar fragmentos.
            db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
            db.commit()

            for chunk_data, emb in zip(chunks, embeddings):
                db.add(
                    Chunk(
                        document_id=doc.id,
                        workspace_id=workspace_id,
                        content=chunk_data["content"],
                        page_number=chunk_data["page_number"],
                        section=chunk_data["section"],
                        chunk_index=chunk_data["chunk_index"],
                        embedding=emb,
                        metadata_json="{}",
                    )
                )

            doc.status = IngestStatus.LISTO
            doc.error_message = None
            db.commit()
            return {"status": "success", "chunks": len(chunks)}

        except Exception as exc:
            if doc is not None:
                doc.status = IngestStatus.FALLIDO
                doc.error_message = f"{type(exc).__name__}: {str(exc)}"[:500]
                db.commit()
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(exc)[:200])
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)
            return {"status": "failed", "error": str(exc)[:300]}
        finally:
            db.close()
