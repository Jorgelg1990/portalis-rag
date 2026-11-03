from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.core.config import settings
from app.models.document import Document, IngestStatus
from app.schemas.document import DocumentUploadResponse, DocumentStatusResponse, DocumentListItem
from app.workers.ingest_tasks import ingest_document
import aiofiles
import os
import uuid
from pathlib import Path

router = APIRouter()

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    workspace_id: str = Form(default="default"),
    db: AsyncSession = Depends(get_db)
):
    # Validate file
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Allowed: {settings.allowed_extensions}")
    
    # Check size
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large")
    
    # Save file
    os.makedirs(settings.upload_dir, exist_ok=True)
    doc_id = uuid.uuid4()
    file_path = os.path.join(settings.upload_dir, f"{doc_id}.{ext}")
    
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(content)
    
    # Create document record
    doc = Document(
        id=doc_id,
        workspace_id=workspace_id,
        filename=file.filename,
        file_path=file_path,
        file_type=ext,
        file_size=len(content),
        status=IngestStatus.PENDIENTE
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    
    # Queue task
    task = ingest_document.delay(str(doc_id), file_path, workspace_id)
    doc.task_id = task.id
    await db.commit()
    
    return DocumentUploadResponse(
        document_id=doc_id,
        filename=file.filename,
        status=doc.status.value,
        task_id=task.id,
        message="Document uploaded and queued for processing"
    )

@router.get("/status/{document_id}", response_model=DocumentStatusResponse)
async def get_status(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentStatusResponse(
        document_id=doc.id,
        filename=doc.filename,
        status=doc.status.value,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at
    )

@router.get("/list", response_model=list[DocumentListItem])
async def list_documents(workspace_id: str = "default", db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.workspace_id == workspace_id).order_by(Document.created_at.desc()))
    docs = result.scalars().all()
    return [
        DocumentListItem(
            document_id=d.id,
            filename=d.filename,
            status=d.status.value,
            file_type=d.file_type,
            created_at=d.created_at
        )
        for d in docs
    ]
