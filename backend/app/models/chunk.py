from sqlalchemy import Column, String, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
import uuid
from app.core.config import settings
from app.core.db import Base

class Chunk(Base):
    __tablename__ = "chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    workspace_id = Column(String, default="default", index=True)
    content = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    section = Column(String, nullable=True)
    chunk_index = Column(Integer, nullable=False)
    embedding = Column(Vector(settings.embedding_dim), nullable=True)
    metadata_json = Column(Text, nullable=True)
