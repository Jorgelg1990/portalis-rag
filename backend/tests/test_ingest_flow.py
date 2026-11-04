"""Ingestion flow end-to-end (parse -> chunk -> embed -> persist) with Celery.

Runs the real task in eager mode against PostgreSQL (skipped when no DB is
reachable, e.g. plain `pytest` on a laptop without docker). The LLM is not
involved: embeddings use the deterministic mock provider.
"""

import os
import tempfile
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.db import Base
from app.models.chunk import Chunk
from app.models.document import Document, IngestStatus
from app.workers import ingest_tasks


def _engine():
    engine = create_engine(settings.sync_database_url, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # no DB available
        pytest.skip(f"PostgreSQL no disponible: {exc}")
    return engine


@pytest.fixture(scope="module")
def session_factory():
    engine = _engine()
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


@pytest.fixture
def docx_file():
    import docx

    path = os.path.join(tempfile.gettempdir(), f"aduanas-{uuid.uuid4().hex}.docx")
    document = docx.Document()
    document.add_heading("Documentación de importación", level=1)
    document.add_paragraph("Los documentos requeridos son la factura comercial y el packing list.")
    document.add_paragraph("La inspección aduanera se realiza en el recinto portuario.")
    document.save(path)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


def test_ingest_flow_with_celery_eager(session_factory, docx_file, monkeypatch):
    # Skip Docling in tests: parsing is covered by the fallback parser here and
    # Docling model downloads would make CI slow and flaky.
    monkeypatch.setattr(settings, "parser", "fallback")
    monkeypatch.setattr(ingest_tasks, "SessionLocal", session_factory)
    ingest_tasks.celery_app.conf.task_always_eager = True
    ingest_tasks.celery_app.conf.task_eager_propagates = True

    db = session_factory()
    doc = Document(
        filename="aduanas.docx",
        file_path=docx_file,
        file_type="docx",
        file_size=os.path.getsize(docx_file),
        status=IngestStatus.PENDIENTE,
        workspace_id="test-ws",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    doc_id = doc.id

    try:
        ingest_tasks.ingest_document.delay(str(doc_id), docx_file, "test-ws")

        db.expire_all()
        refreshed = db.query(Document).filter(Document.id == doc_id).first()
        assert refreshed.status == IngestStatus.LISTO
        assert refreshed.error_message is None

        chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(chunks) >= 1
        assert all(c.workspace_id == "test-ws" for c in chunks)
        assert all(c.content.strip() for c in chunks)
        assert all(len(c.embedding) == settings.embedding_dim for c in chunks)
        assert any(c.section == "Documentación de importación" for c in chunks)

        # Idempotency: re-running the task must not duplicate fragments.
        ingest_tasks.ingest_document.delay(str(doc_id), docx_file, "test-ws")
        db.expire_all()
        chunks_again = db.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(chunks_again) == len(chunks)
    finally:
        db.query(Chunk).filter(Chunk.document_id == doc_id).delete()
        db.query(Document).filter(Document.id == doc_id).delete()
        db.commit()
        db.close()
