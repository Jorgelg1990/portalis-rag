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
    created_at: datetime
