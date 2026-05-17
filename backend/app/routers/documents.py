import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cache import response_cache
from app.config import settings
from app.db.session import get_pg_db as get_db
from app.db.models.rag_document import RagDocument as Document
from app.db.models.rag_document_image import RagDocumentImage as DocumentImage
from app.schemas import DocumentDetail, DocumentSummary, DocumentsListResponse
from app.services import file_storage, vector_store
from app.services.ingest_pipeline import cancel_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents", response_model=DocumentsListResponse)
async def list_documents(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(select(func.count()).select_from(Document))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Document)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    docs = result.scalars().all()

    return DocumentsListResponse(
        items=[DocumentSummary.model_validate(d) for d in docs],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Document)
        .where(Document.id == uuid.UUID(doc_id))
        .options(
            selectinload(Document.chunks),
            selectinload(Document.images),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentDetail.model_validate(doc)


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, uuid.UUID(doc_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    cancel_pipeline(doc_id)

    n = await asyncio.to_thread(response_cache.invalidate_by_doc_id, doc_id)
    if n:
        logger.info("Eliminado doc_id=%s: invalidadas %d respuestas cacheadas", doc_id, n)

    try:
        await vector_store.delete_by_doc_id(doc_id)
    except Exception as exc:
        logger.warning("doc_id=%s: ChromaDB delete partial failure: %s", doc_id, exc)

    try:
        await file_storage.delete_objects_with_prefix(
            settings.minio_bucket_documents, f"{doc_id}/"
        )
        await file_storage.delete_objects_with_prefix(
            settings.minio_bucket_images, f"{doc_id}/"
        )
    except Exception as exc:
        logger.warning("doc_id=%s: storage delete partial failure: %s", doc_id, exc)

    await db.delete(doc)
    await db.commit()
    logger.info("Deleted document doc_id=%s", doc_id)


@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, dl: bool = False, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.minio_path:
        raise HTTPException(status_code=404, detail="File not available for download")

    try:
        data = await file_storage.get_object_bytes(settings.minio_bucket_documents, doc.minio_path)
    except Exception as exc:
        logger.error("Failed to retrieve document %s: %s", doc_id, exc)
        raise HTTPException(status_code=502, detail="Failed to retrieve file from storage")

    ext = doc.original_filename.rsplit(".", 1)[-1].lower() if "." in doc.original_filename else ""
    content_type_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "txt": "text/plain",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")
    safe_filename = doc.original_filename.replace('"', "_")
    disposition = "attachment" if dl else "inline"

    return StreamingResponse(
        iter([data]),
        media_type=content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe_filename}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/images/{image_id}")
async def get_image(image_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DocumentImage).where(DocumentImage.id == uuid.UUID(image_id))
    )
    img = result.scalar_one_or_none()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    try:
        data = await file_storage.get_object_bytes(
            settings.minio_bucket_images, img.minio_path
        )
    except Exception as exc:
        logger.error("Failed to retrieve image %s: %s", image_id, exc)
        raise HTTPException(status_code=502, detail="Failed to retrieve image from storage")

    ext = img.minio_path.rsplit(".", 1)[-1].lower() if "." in img.minio_path else "png"
    content_type = f"image/{ext}" if ext in ("png", "jpg", "jpeg", "webp") else "image/png"

    return StreamingResponse(
        iter([data]),
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )
