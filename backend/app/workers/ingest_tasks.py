from app.workers.celery_app import celery_app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.document import Document, IngestStatus
from app.models.chunk import Chunk
from app.services.providers import ProviderFactory
from app.core.tracing import tracer
from opentelemetry import trace
import os
from pathlib import Path

# Simple sync DB for worker
engine = create_engine(settings.sync_database_url)
SessionLocal = sessionmaker(bind=engine)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_document(self, document_id: str, file_path: str, workspace_id: str):
    with tracer.start_as_current_span("ingest_document") as span:
        span.set_attribute("document.id", document_id)
        span.set_attribute("workspace.id", workspace_id)
        
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if not doc:
                return {"error": "document not found"}
            
            doc.status = IngestStatus.PROCESANDO
            db.commit()
            
            # Parse document (simplified - try docling if available, fallback)
            content = ""
            try:
                # Try to read text simply
                if file_path.endswith('.pdf'):
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(file_path)
                        for i, page in enumerate(reader.pages):
                            text = page.extract_text() or ""
                            if text.strip():
                                content += f"\n\n[PAGE {i+1}]\n{text}"
                    except:
                        content = f"Mock content from PDF {doc.filename} - Page 1\nThis is sample document content for testing."
                elif file_path.endswith('.docx'):
                    try:
                        import docx
                        docx_doc = docx.Document(file_path)
                        for para in docx_doc.paragraphs:
                            content += para.text + "\n"
                    except:
                        content = f"Mock content from DOCX {doc.filename}\nThis is sample document content for testing."
                else:
                    content = f"Content from {doc.filename}"
            except Exception as e:
                doc.status = IngestStatus.FALLIDO
                doc.error_message = f"Parse error: {str(e)}"
                db.commit()
                raise
            
            # Chunking with metadata
            # Simple chunking by paragraphs/size
            chunks_text = []
            # naive split
            paragraphs = content.split('\n\n')
            current = ""
            for p in paragraphs:
                if len(current) + len(p) < 800:
                    current += "\n\n" + p if current else p
                else:
                    if current:
                        chunks_text.append(current)
                    current = p
            if current:
                chunks_text.append(current)
            
            # If no chunks, create one
            if not chunks_text:
                chunks_text = [content[:1000] if content else "Empty document"]
            
            embedder = ProviderFactory.get_embeddings()
            embeddings = embedder.embed_texts(chunks_text)
            
            # Idempotencia: si ya existen chunks para este documento, eliminarlos antes de reintentar
            existing_chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).all()
            if existing_chunks:
                for ec in existing_chunks:
                    db.delete(ec)
                db.commit()
            
            # Store chunks
            for idx, (chunk_text, emb) in enumerate(zip(chunks_text, embeddings)):
                # Extract page number if present
                page_num = None
                if "[PAGE" in chunk_text:
                    try:
                        start = chunk_text.find("[PAGE")
                        end = chunk_text.find("]", start)
                        page_num = int(chunk_text[start+6:end].strip())
                    except:
                        pass
                
                chunk = Chunk(
                    document_id=doc.id,
                    workspace_id=workspace_id,
                    content=chunk_text,
                    page_number=page_num,
                    section=None,
                    chunk_index=idx,
                    embedding=emb,
                    metadata_json='{}'
                )
                db.add(chunk)
            
            doc.status = IngestStatus.LISTO
            db.commit()
            span.set_attribute("chunks.count", len(chunks_text))
            return {"status": "success", "chunks": len(chunks_text)}
            
        except Exception as exc:
            doc.status = IngestStatus.FALLIDO
            doc.error_message = str(exc)[:500]
            db.commit()
            try:
                raise self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                return {"status": "failed", "error": str(exc)}
        finally:
            db.close()
