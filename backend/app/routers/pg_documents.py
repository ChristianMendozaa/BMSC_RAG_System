import mimetypes
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
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
from app.services import file_storage, hard_delete
from app.services.ingest_pipeline import ACCEPTED_EXTENSIONS, run_pipeline

router = APIRouter(prefix="/api", tags=["pg-documents"])

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB


class PgDocumentOut(BaseModel):
    doc_id: str
    title: str
    collection_id: str | None
    collection_name: str | None
    original_filename: str
    mime_type: str
    file_size_bytes: int
    pg_status: str
    rag_status: str
    rag_chunk_count: int
    rag_image_count: int
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    collection_id: str | None
    status: str


class DocumentPatch(BaseModel):
    title: str | None = None
    collection_id: uuid.UUID | None = None
    clear_collection: bool = False  # explícito para distinguir "no cambies" de "ponlo en null"


@router.get("/pg-documents", response_model=list[PgDocumentOut])
async def list_pg_documents(
    search: str | None = Query(None, description="Busca en título"),
    collection_id: uuid.UUID | None = Query(None),
    status: Literal["ACTIVE", "OBSOLETE"] | None = Query(None),
    uncategorized: bool = Query(False, description="Solo documentos sin colección"),
    sort: Literal["newest", "oldest_obsolete", "name"] = Query("newest"),
    pg_db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(get_current_user),
):
    stmt = select(PGDocument).options(selectinload(PGDocument.versions))

    if search:
        like = f"%{search.lower()}%"
        # title llega ya con el nombre del archivo, basta con LIKE case-insensitive
        stmt = stmt.where(func.lower(PGDocument.title).like(like))
    if uncategorized:
        stmt = stmt.where(PGDocument.collection_id.is_(None))
    elif collection_id is not None:
        stmt = stmt.where(PGDocument.collection_id == collection_id)
    if status is not None:
        stmt = stmt.where(PGDocument.status == status)

    if sort == "oldest_obsolete":
        # Obsoletos primero, los más antiguos arriba
        stmt = stmt.order_by(
            (PGDocument.status == "OBSOLETE").desc(),
            PGDocument.updated_at.asc(),
        )
    elif sort == "name":
        stmt = stmt.order_by(PGDocument.title.asc())
    else:
        stmt = stmt.order_by(PGDocument.created_at.desc())

    result = await pg_db.execute(stmt)
    pg_docs = result.scalars().all()

    # Load collection names (solo las que existen)
    col_ids = list({d.collection_id for d in pg_docs if d.collection_id is not None})
    if col_ids:
        col_result = await pg_db.execute(
            select(Collection).where(Collection.id.in_(col_ids))
        )
        col_map = {c.id: c.name for c in col_result.scalars()}
    else:
        col_map = {}

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
                collection_id=str(doc.collection_id) if doc.collection_id else None,
                collection_name=col_map.get(doc.collection_id) if doc.collection_id else None,
                original_filename=current_version.original_filename,
                mime_type=current_version.mime_type,
                file_size_bytes=current_version.file_size_bytes,
                pg_status=str(doc.status),
                rag_status=rag_doc.status if rag_doc else "sin_rag",
                rag_chunk_count=rag_doc.chunk_count if rag_doc else 0,
                rag_image_count=rag_doc.image_count if rag_doc else 0,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
            )
        )
    return items


async def _do_upload(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    pg_db: AsyncSession,
    current_user: PGUser,
    collection_id: uuid.UUID | None,
) -> UploadResponse:
    has_perm = current_user.role.is_system or current_user.role.can_upload_documents
    if not has_perm:
        raise HTTPException(status_code=403, detail="Se requiere permiso para subir documentos")

    if collection_id is not None:
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
        collection_id=str(collection_id) if collection_id else None,
        status="pending",
    )


@router.post("/collections/{collection_id}/upload", response_model=UploadResponse, status_code=201)
async def upload_to_collection(
    collection_id: uuid.UUID,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    pg_db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(get_current_user),
):
    return await _do_upload(file, background_tasks, pg_db, current_user, collection_id)


@router.post("/pg-documents/upload", response_model=UploadResponse, status_code=201)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    collection_id: str | None = Form(None),
    pg_db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(get_current_user),
):
    """Upload sin colección obligatoria. collection_id vacío → 'Sin asignar'."""
    parsed: uuid.UUID | None = None
    if collection_id:
        try:
            parsed = uuid.UUID(collection_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="collection_id inválido")
    return await _do_upload(file, background_tasks, pg_db, current_user, parsed)


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
    """Soft-delete: marca el documento como OBSOLETE. Sigue siendo descargable."""
    has_perm = current_user.role.is_system or current_user.role.can_delete_documents
    if not has_perm:
        raise HTTPException(status_code=403, detail="Se requiere permiso para eliminar documentos")

    pg_doc = await pg_db.scalar(select(PGDocument).where(PGDocument.id == doc_id))
    if not pg_doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    pg_doc.status = "OBSOLETE"
    await pg_db.commit()


@router.patch("/pg-documents/{doc_id}", response_model=PgDocumentOut)
async def patch_pg_document(
    doc_id: uuid.UUID,
    body: DocumentPatch,
    pg_db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(get_current_user),
):
    """Actualiza título y/o colección (incluye mover a 'Sin colección')."""
    has_perm = current_user.role.is_system or current_user.role.can_upload_documents
    if not has_perm:
        raise HTTPException(status_code=403, detail="Se requiere permiso para modificar documentos")

    pg_doc = await pg_db.scalar(
        select(PGDocument).where(PGDocument.id == doc_id).options(selectinload(PGDocument.versions))
    )
    if not pg_doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if body.title is not None:
        pg_doc.title = body.title

    if body.clear_collection:
        pg_doc.collection_id = None
    elif body.collection_id is not None:
        col = await pg_db.scalar(select(Collection).where(Collection.id == body.collection_id))
        if not col or not col.is_active:
            raise HTTPException(status_code=404, detail="Colección destino no encontrada o inactiva")
        pg_doc.collection_id = body.collection_id

    await pg_db.commit()
    await pg_db.refresh(pg_doc)

    current_version = next((v for v in pg_doc.versions if v.is_current), None)
    rag_doc = await pg_db.scalar(select(RagDocument).where(RagDocument.id == doc_id))
    col_name = None
    if pg_doc.collection_id:
        col_name = await pg_db.scalar(
            select(Collection.name).where(Collection.id == pg_doc.collection_id)
        )
    return PgDocumentOut(
        doc_id=str(pg_doc.id),
        title=pg_doc.title,
        collection_id=str(pg_doc.collection_id) if pg_doc.collection_id else None,
        collection_name=col_name,
        original_filename=current_version.original_filename if current_version else pg_doc.title,
        mime_type=current_version.mime_type if current_version else "application/octet-stream",
        file_size_bytes=current_version.file_size_bytes if current_version else 0,
        pg_status=str(pg_doc.status),
        rag_status=rag_doc.status if rag_doc else "sin_rag",
        rag_chunk_count=rag_doc.chunk_count if rag_doc else 0,
        rag_image_count=rag_doc.image_count if rag_doc else 0,
        created_at=pg_doc.created_at,
        updated_at=pg_doc.updated_at,
    )


@router.post("/pg-documents/{doc_id}/reactivate", status_code=204)
async def reactivate_pg_document(
    doc_id: uuid.UUID,
    pg_db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(get_current_user),
):
    """Devuelve un documento OBSOLETE a estado ACTIVE."""
    has_perm = current_user.role.is_system or current_user.role.can_upload_documents
    if not has_perm:
        raise HTTPException(status_code=403, detail="Se requiere permiso para modificar documentos")

    pg_doc = await pg_db.scalar(select(PGDocument).where(PGDocument.id == doc_id))
    if not pg_doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    if str(pg_doc.status) != "OBSOLETE":
        raise HTTPException(status_code=400, detail="El documento no está obsoleto")

    pg_doc.status = "ACTIVE"
    await pg_db.commit()


@router.delete("/pg-documents/{doc_id}/permanent", status_code=204)
async def permanent_delete_pg_document(
    doc_id: uuid.UUID,
    pg_db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(get_current_user),
):
    """
    Hard delete: borra archivos físicos, vectores en ChromaDB y todas las
    filas asociadas. Solo permitido sobre documentos OBSOLETE para forzar el
    flujo "obsoletizar primero → confirmar después".
    """
    has_perm = current_user.role.is_system or current_user.role.can_delete_documents
    if not has_perm:
        raise HTTPException(status_code=403, detail="Se requiere permiso para eliminar documentos")

    pg_doc = await pg_db.scalar(select(PGDocument).where(PGDocument.id == doc_id))
    if not pg_doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    if str(pg_doc.status) != "OBSOLETE":
        raise HTTPException(
            status_code=400,
            detail="Solo se puede eliminar permanentemente un documento obsoleto. Márquelo como obsoleto primero.",
        )

    await hard_delete.hard_delete_document(pg_db, doc_id)
    await pg_db.commit()
