from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.core.config import settings
from app.models.document import Document, IngestStatus
from app.models.chunk import Chunk
from app.schemas.document import (
    ChunkDetail,
    DocumentUploadResponse,
    DocumentStatusResponse,
    DocumentListItem,
)
from app.workers.ingest_tasks import ingest_document
import aiofiles
import os
import uuid

router = APIRouter()

WORKSPACE_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

_MAGIC = {
    "pdf": b"%PDF-",
    "docx": b"PK\x03\x04",
}


def _validate_signature(ext: str, content: bytes) -> None:
    """Reject files whose bytes do not match the declared extension."""
    expected = _MAGIC.get(ext)
    if expected and not content.startswith(expected):
        raise HTTPException(
            status_code=400,
            detail=f"El contenido del archivo no coincide con la extensión .{ext}",
        )


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    workspace_id: str = Form(default="default", pattern=WORKSPACE_PATTERN),
    db: AsyncSession = Depends(get_db),
):
    filename = (file.filename or "").strip()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de archivo no permitido. Permitidos: {settings.allowed_extensions}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"El archivo supera el límite de {settings.max_upload_mb} MB",
        )
    _validate_signature(ext, content)

    # The stored name is a UUID: user input never reaches the filesystem.
    os.makedirs(settings.upload_dir, exist_ok=True)
    doc_id = uuid.uuid4()
    file_path = os.path.join(settings.upload_dir, f"{doc_id}.{ext}")

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    doc = Document(
        id=doc_id,
        workspace_id=workspace_id,
        filename=filename[:255],
        file_path=file_path,
        file_type=ext,
        file_size=len(content),
        status=IngestStatus.PENDIENTE,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    try:
        task = ingest_document.delay(str(doc_id), file_path, workspace_id)
    except Exception as exc:  # broker down: leave a consistent state
        doc.status = IngestStatus.FALLIDO
        doc.error_message = f"No se pudo encolar la ingesta: {type(exc).__name__}"
        await db.commit()
        raise HTTPException(status_code=503, detail="Cola de ingesta no disponible") from exc

    doc.task_id = task.id
    await db.commit()

    return DocumentUploadResponse(
        document_id=doc_id,
        filename=filename,
        status=IngestStatus.PENDIENTE.value,
        task_id=task.id,
        message="Documento subido y encolado para procesamiento",
    )


@router.get("/status/{document_id}", response_model=DocumentStatusResponse)
async def get_status(
    document_id: uuid.UUID,
    workspace_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.workspace_id == workspace_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return DocumentStatusResponse(
        document_id=doc.id,
        filename=doc.filename,
        status=doc.status.value,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get("/list", response_model=list[DocumentListItem])
async def list_documents(
    workspace_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    return [
        DocumentListItem(
            document_id=d.id,
            filename=d.filename,
            status=d.status.value,
            file_type=d.file_type,
            error_message=d.error_message,
            created_at=d.created_at,
        )
        for d in docs
    ]


@router.get("/chunks/{chunk_id}", response_model=ChunkDetail)
async def get_chunk(
    chunk_id: uuid.UUID,
    workspace_id: str = "default",
    db: AsyncSession = Depends(get_db),
):
    """Full fragment text, used by the UI to open the cited source."""
    result = await db.execute(
        select(Chunk).where(Chunk.id == chunk_id, Chunk.workspace_id == workspace_id)
    )
    chunk = result.scalar_one_or_none()
    if not chunk:
        raise HTTPException(status_code=404, detail="Fragmento no encontrado")
    return ChunkDetail(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        workspace_id=chunk.workspace_id,
        content=chunk.content,
        page_number=chunk.page_number,
        section=chunk.section,
        chunk_index=chunk.chunk_index,
    )
