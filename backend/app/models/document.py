from sqlalchemy import Column, String, Integer, DateTime, Text, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from app.core.db import Base

class IngestStatus(str, enum.Enum):
    PENDIENTE = "pendiente"
    PROCESANDO = "procesando"
    FALLIDO = "fallido"
    LISTO = "listo"

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(String, default="default", index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    status = Column(
        Enum(IngestStatus, values_callable=lambda e: [m.value for m in e], name="ingest_status"),
        default=IngestStatus.PENDIENTE,
        index=True,
    )
    error_message = Column(Text, nullable=True)
    task_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
