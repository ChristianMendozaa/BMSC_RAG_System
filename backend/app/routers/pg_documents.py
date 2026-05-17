import mimetypes
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.models.collection import Collection
from app.db.models.document import PGDocument
from app.db.models.document_version import DocumentVersion
from app.db.models.rag_document import RagDocument
from app.db.models.user import PGUser
from app.db.session import get_pg_db
from app.dependencies import get_current_user
from app.services import file_storage
from app.services.ingest_pipeline import ACCEPTED_EXTENSIONS, run_pipeline

router = APIRouter(prefix="/api", tags=["pg-documents"])

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB


class PgDocumentOut(BaseModel):
    doc_id: str
    title: str
    collection_id: str
    collection_name: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    pg_status: str
    rag_status: str
    rag_chunk_count: int
    rag_image_count: int
    created_at: datetime


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    collection_id: str
    status: str


@router.get("/pg-documents", response_model=list[PgDocumentOut])
async def list_pg_documents(
    pg_db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(get_current_user),
):
    result = await pg_db.execute(
        select(PGDocument)
        .options(selectinload(PGDocument.versions))
        .order_by(PGDocument.created_at.desc())
    )
    pg_docs = result.scalars().all()

    # Load collection names
    col_ids = list({d.collection_id for d in pg_docs})
    col_result = await pg_db.execute(
        select(Collection).where(Collection.id.in_(col_ids))
    )
    col_map = {c.id: c.name for c in col_result.scalars()}

    # Load RAG status from PostgreSQL rag_documents
    doc_uuids = [d.id for d in pg_docs]
    if doc_uuids:
        rag_result = await pg_db.execute(
            select(RagDocument).where(RagDocument.id.in_(doc_uuids))
        )
        rag_map = {r.id: r for r in rag_result.scalars()}
    else:
        rag_map = {}

    items = []
    for doc in pg_docs:
        current_version = next((v for v in doc.versions if v.is_current), None)
        if not current_version:
            continue

        rag_doc = rag_map.get(doc.id)
        items.append(
            PgDocumentOut(
                doc_id=str(doc.id),
                title=doc.title,
                collection_id=str(doc.collection_id),
                collection_name=col_map.get(doc.collection_id, "—"),
                original_filename=current_version.original_filename,
                mime_type=current_version.mime_type,
                file_size_bytes=current_version.file_size_bytes,
                pg_status=str(doc.status),
                rag_status=rag_doc.status if rag_doc else "sin_rag",
                rag_chunk_count=rag_doc.chunk_count if rag_doc else 0,
                rag_image_count=rag_doc.image_count if rag_doc else 0,
                created_at=doc.created_at,
            )
        )
    return items


@router.post("/collections/{collection_id}/upload", response_model=UploadResponse, status_code=201)
async def upload_to_collection(
    collection_id: uuid.UUID,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    pg_db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(get_current_user),
):
    has_perm = current_user.role.is_system or current_user.role.can_upload_documents
    if not has_perm:
        raise HTTPException(status_code=403, detail="Se requiere permiso para subir documentos")

    col = await pg_db.scalar(select(Collection).where(Collection.id == collection_id))
    if not col or not col.is_active:
        raise HTTPException(status_code=404, detail="Colección no encontrada o inactiva")

    filename = file.filename or "unnamed"
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in ACCEPTED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo de archivo no soportado '{ext}'. Aceptados: {', '.join(sorted(ACCEPTED_EXTENSIONS))}",
        )

    file_bytes = await file.read()
    file_size = len(file_bytes)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máx. 200 MB)")

    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    doc_id = uuid.uuid4()
    doc_id_str = str(doc_id)
    object_name = f"{doc_id_str}/v1/{filename}"

    await file_storage.upload_bytes(settings.minio_bucket_documents, object_name, file_bytes, mime_type)

    # PGDocument (lógico, colección)
    pg_doc = PGDocument(
        id=doc_id,
        title=filename,
        collection_id=collection_id,
        status="ACTIVE",
        created_by=current_user.id,
    )
    pg_db.add(pg_doc)

    # DocumentVersion (versión física del archivo)
    doc_version = DocumentVersion(
        document_id=doc_id,
        version_number=1,
        original_filename=filename,
        file_path=object_name,
        file_size_bytes=file_size,
        mime_type=mime_type,
        is_current=True,
        index_status="PENDING",
        created_by=current_user.id,
    )
    pg_db.add(doc_version)

    # RagDocument (tracking del pipeline RAG — mismo UUID que PGDocument)
    rag_doc = RagDocument(
        id=doc_id,
        filename=filename,
        original_filename=filename,
        file_type=ext.lstrip("."),
        file_size=file_size,
        status="pending",
    )
    pg_db.add(rag_doc)

    await pg_db.commit()

    background_tasks.add_task(run_pipeline, doc_id_str, file_bytes, filename)

    return UploadResponse(
        doc_id=doc_id_str,
        filename=filename,
        collection_id=str(collection_id),
        status="pending",
    )


@router.get("/pg-documents/{doc_id}/download")
async def download_pg_document(
    doc_id: uuid.UUID,
    pg_db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(get_current_user),
):
    pg_doc = await pg_db.scalar(
        select(PGDocument)
        .where(PGDocument.id == doc_id)
        .options(selectinload(PGDocument.versions))
    )
    if not pg_doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    current_version = next((v for v in pg_doc.versions if v.is_current), None)
    if not current_version:
        raise HTTPException(status_code=404, detail="Versión actual no encontrada")

    try:
        data = await file_storage.get_object_bytes(
            settings.minio_bucket_documents, current_version.file_path
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error al leer el archivo: {exc}")

    safe_filename = current_version.original_filename.replace('"', '_')
    return StreamingResponse(
        iter([data]),
        media_type=current_version.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "Cache-Control": "private, no-cache",
        },
    )


@router.delete("/pg-documents/{doc_id}", status_code=204)
async def delete_pg_document(
    doc_id: uuid.UUID,
    pg_db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(get_current_user),
):
    has_perm = current_user.role.is_system or current_user.role.can_delete_documents
    if not has_perm:
        raise HTTPException(status_code=403, detail="Se requiere permiso para eliminar documentos")

    pg_doc = await pg_db.scalar(select(PGDocument).where(PGDocument.id == doc_id))
    if not pg_doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    pg_doc.status = "OBSOLETE"
    await pg_db.commit()
