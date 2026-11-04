import os,tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.document import Document,IngestStatus
from app.models.chunk import Chunk
from app.workers import ingest_tasks
from app.core.db import Base
os.environ['CELERY_TASK_ALWAYS_EAGER']='True'
os.environ['CELERY_EAGER_PROPAGATES_EXCEPTIONS']='True'
ingest_tasks.celery_app.conf.task_always_eager=True
ingest_tasks.celery_app.conf.task_eager_propagates=True

def test_ingest_flow_with_celery_eager():
    engine=create_engine('sqlite:///:memory:',connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine)
    ingest_tasks.SessionLocal=Session
    db=Session()
    f=tempfile.NamedTemporaryFile(mode='w',suffix='.txt',delete=False,encoding='utf-8')
    f.write('Procedimientos de aduanas. Test de ingesta con Celery.')
    f.close()
    try:
        doc=Document(filename='test-aduanas.txt',file_path=f.name,file_type='txt',file_size=100,status=IngestStatus.PENDIENTE,workspace_id='default')
        db.add(doc); db.commit(); db.refresh(doc)
        result=ingest_tasks.ingest_document.delay(str(doc.id),f.name,'default')
        assert result.successful()
        db.expire_all()
        doc_check=db.query(Document).filter(Document.id==doc.id).first()
        assert doc_check.status==IngestStatus.LISTO
        chunks=db.query(Chunk).filter(Chunk.document_id==doc.id).all()
        assert len(chunks)>0
    finally:
        db.close()
        try: os.unlink(f.name)
        except: pass
        engine.dispose()
