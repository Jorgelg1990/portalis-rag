from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

class DocumentUploadResponse(BaseModel):
    document_id: UUID
    filename: str
    status: str
    task_id: Optional[str] = None
    message: str

class DocumentStatusResponse(BaseModel):
    document_id: UUID
    filename: str
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

class DocumentListItem(BaseModel):
    document_id: UUID
    filename: str
    status: str
    file_type: str
    error_message: Optional[str] = None
    created_at: datetime

class ChunkDetail(BaseModel):
    chunk_id: UUID
    document_id: UUID
    workspace_id: str
    content: str
    page_number: Optional[int] = None
    section: Optional[str] = None
    chunk_index: int
