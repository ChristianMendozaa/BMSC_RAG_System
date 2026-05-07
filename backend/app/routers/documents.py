import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import Document, DocumentImage
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
        .where(Document.id == doc_id)
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
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Signal any in-flight ingestion pipeline to abort at its next checkpoint
    cancel_pipeline(doc_id)

    try:
        await vector_store.delete_by_doc_id(doc_id)
    except Exception as exc:
        logger.warning("doc_id=%s: Qdrant delete partial failure: %s", doc_id, exc)

    try:
        await file_storage.delete_objects_with_prefix(
            settings.minio_bucket_documents, f"{doc_id}/"
        )
        await file_storage.delete_objects_with_prefix(
            settings.minio_bucket_images, f"{doc_id}/"
        )
    except Exception as exc:
        logger.warning("doc_id=%s: MinIO delete partial failure: %s", doc_id, exc)

    await db.delete(doc)
    await db.commit()
    logger.info("Deleted document doc_id=%s", doc_id)


@router.get("/images/{image_id}")
async def get_image(image_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DocumentImage).where(DocumentImage.id == image_id)
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
