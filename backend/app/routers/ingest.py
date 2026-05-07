import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Document
from app.schemas import DocumentStatusOut, IngestResponse
from app.services.ingest_pipeline import ACCEPTED_EXTENSIONS, run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ingest"])

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    filename = file.filename or "unnamed"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ACCEPTED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(ACCEPTED_EXTENSIONS))}",
        )

    file_bytes = await file.read()
    file_size = len(file_bytes)

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 200 MB)")

    doc_id = str(uuid.uuid4())
    doc = Document(
        id=doc_id,
        filename=filename,
        original_filename=filename,
        file_type=ext.lstrip("."),
        file_size=file_size,
        status="pending",
    )
    db.add(doc)
    await db.commit()

    background_tasks.add_task(run_pipeline, doc_id, file_bytes, filename)

    logger.info("Queued ingestion for doc_id=%s filename=%s", doc_id, filename)
    return IngestResponse(doc_id=doc_id, filename=filename, status="pending")


@router.get("/documents/{doc_id}/status", response_model=DocumentStatusOut)
async def get_document_status(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentStatusOut(
        id=doc.id,
        status=doc.status,
        error_message=doc.error_message,
        chunk_count=doc.chunk_count,
        image_count=doc.image_count,
    )
