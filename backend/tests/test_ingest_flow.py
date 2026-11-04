"""Flujo de ingesta completo ejecutando la tarea de Celery en modo eager.

Usa sqlite en memoria para aislar el test de una DB externa; el objetivo es
verificar el flujo de la tarea (parse -> chunk -> embed -> persist -> estado).
La integración real con pgvector se cubre en test_pgvector_integration.py.
"""

import os
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.chunk import Chunk
from app.models.document import Document, IngestStatus
from app.workers import ingest_tasks

os.environ["CELERY_TASK_ALWAYS_EAGER"] = "True"
os.environ["CELERY_EAGER_PROPAGATES_EXCEPTIONS"] = "True"
ingest_tasks.celery_app.conf.task_always_eager = True
ingest_tasks.celery_app.conf.task_eager_propagates = True


def test_ingest_flow_with_celery_eager(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(ingest_tasks, "SessionLocal", Session)

    db = Session()
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    tmp.write("Procedimientos de aduanas. Test de ingesta con Celery.")
    tmp.close()

    try:
        doc = Document(
            filename="test-aduanas.txt",
            file_path=tmp.name,
            file_type="txt",
            file_size=100,
            status=IngestStatus.PENDIENTE,
            workspace_id="default",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id

        result = ingest_tasks.ingest_document.delay(str(doc_id), tmp.name, "default")
        assert result.successful()

        db.expire_all()
        refreshed = db.query(Document).filter(Document.id == doc_id).first()
        assert refreshed.status == IngestStatus.LISTO
        assert refreshed.error_message is None

        chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(chunks) > 0
        assert all(c.workspace_id == "default" for c in chunks)
        assert all(c.content for c in chunks)

        # idempotencia: re-ejecutar no debe duplicar chunks
        ingest_tasks.ingest_document.delay(str(doc_id), tmp.name, "default")
        db.expire_all()
        chunks_again = db.query(Chunk).filter(Chunk.document_id == doc_id).all()
        assert len(chunks_again) == len(chunks)
    finally:
        db.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        engine.dispose()
