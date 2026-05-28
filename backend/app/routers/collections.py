import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.models.collection import Collection
from app.db.models.collection_permission import CollectionPermission
from app.db.models.document import PGDocument
from app.db.models.document_version import DocumentVersion
from app.db.models.rag_document import RagDocument
from app.db.models.role_document_permission import RoleDocumentPermission
from app.db.models.user import PGUser
from app.db.models.user_collection_permission import UserCollectionPermission
from app.db.models.user_document_permission import UserDocumentPermission
from app.db.schemas.collection import CollectionCreate, CollectionOut, CollectionUpdate
from app.db.schemas.permission import AccessibleCollectionOut, AccessibleDocumentOut
from app.db.session import get_pg_db
from app.dependencies import get_current_user
from app.services import hard_delete

router = APIRouter(prefix="/api/collections", tags=["collections"])

_manage_dep = require_permission("can_manage_collections")


@router.get("/accessible", response_model=list[AccessibleCollectionOut])
async def get_accessible_collections(
    db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(get_current_user),
):
    """
    Devuelve las colecciones activas con los documentos a los que el usuario tiene can_view.
    Usuarios con can_manage_collections ven todo.
    Para el resto se aplica el orden de resolución de permisos.
    """
    # Obtener todas las colecciones activas
    cols_result = await db.execute(
        select(Collection).where(Collection.is_active == True).order_by(Collection.name)
    )
    all_collections = cols_result.scalars().all()

    if current_user.role.can_manage_collections:
        # Admins ven todas las colecciones y todos los documentos activos con RAG listo
        out = []
        for col in all_collections:
            docs_result = await db.execute(
                select(PGDocument, DocumentVersion)
                .join(
                    DocumentVersion,
                    and_(
                        DocumentVersion.document_id == PGDocument.id,
                        DocumentVersion.is_current == True,
                    ),
                )
                .join(
                    RagDocument,
                    and_(
                        RagDocument.id == PGDocument.id,
                        RagDocument.status == "ready",
                    ),
                )
                .where(PGDocument.collection_id == col.id, PGDocument.status == "ACTIVE")
                .order_by(PGDocument.title)
            )
            accessible_docs = [
                AccessibleDocumentOut(
                    doc_id=doc.id,
                    title=doc.title,
                    original_filename=ver.original_filename,
                    mime_type=ver.mime_type,
                )
                for doc, ver in docs_result.all()
            ]
            out.append(
                AccessibleCollectionOut(
                    id=col.id,
                    name=col.name,
                    description=col.description,
                    documents=accessible_docs,
                )
            )
        return out

    # Cargar todos los permisos relevantes en memoria (evita N queries por doc)
    udp_res = await db.execute(
        select(UserDocumentPermission).where(UserDocumentPermission.user_id == current_user.id)
    )
    udp_map: dict[uuid.UUID, UserDocumentPermission] = {p.document_id: p for p in udp_res.scalars()}

    rdp_res = await db.execute(
        select(RoleDocumentPermission).where(RoleDocumentPermission.role_id == current_user.role_id)
    )
    rdp_map: dict[uuid.UUID, RoleDocumentPermission] = {p.document_id: p for p in rdp_res.scalars()}

    ucp_res = await db.execute(
        select(UserCollectionPermission).where(UserCollectionPermission.user_id == current_user.id)
    )
    ucp_map: dict[uuid.UUID, UserCollectionPermission] = {p.collection_id: p for p in ucp_res.scalars()}

    cp_res = await db.execute(
        select(CollectionPermission).where(CollectionPermission.role_id == current_user.role_id)
    )
    cp_map: dict[uuid.UUID, CollectionPermission] = {p.collection_id: p for p in cp_res.scalars()}

    def _can_view_doc(doc_id: uuid.UUID, col_id: uuid.UUID) -> bool:
        if doc_id in udp_map:
            return udp_map[doc_id].can_view
        if doc_id in rdp_map:
            return rdp_map[doc_id].can_view
        if col_id in ucp_map:
            return ucp_map[col_id].can_view
        if col_id in cp_map:
            return cp_map[col_id].can_view
        return False

    out = []
    for col in all_collections:
        docs_result = await db.execute(
            select(PGDocument, DocumentVersion)
            .join(
                DocumentVersion,
                and_(
                    DocumentVersion.document_id == PGDocument.id,
                    DocumentVersion.is_current == True,
                ),
            )
            .join(
                RagDocument,
                and_(
                    RagDocument.id == PGDocument.id,
                    RagDocument.status == "ready",
                ),
            )
            .where(PGDocument.collection_id == col.id, PGDocument.status == "ACTIVE")
            .order_by(PGDocument.title)
        )
        accessible_docs = [
            AccessibleDocumentOut(
                doc_id=doc.id,
                title=doc.title,
                original_filename=ver.original_filename,
                mime_type=ver.mime_type,
            )
            for doc, ver in docs_result.all()
            if _can_view_doc(doc.id, col.id)
        ]

        col_level_can_view = (
            (col.id in ucp_map and ucp_map[col.id].can_view)
            or (col.id in cp_map and cp_map[col.id].can_view)
        )

        if col_level_can_view or accessible_docs:
            out.append(
                AccessibleCollectionOut(
                    id=col.id,
                    name=col.name,
                    description=col.description,
                    documents=accessible_docs,
                )
            )

    return out


@router.get("", response_model=list[CollectionOut])
async def list_collections(
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(get_current_user),
):
    result = await db.execute(
        select(Collection).order_by(Collection.name)
    )
    return result.scalars().all()


@router.post("", response_model=CollectionOut, status_code=201)
async def create_collection(
    body: CollectionCreate,
    db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(_manage_dep),
):
    existing = await db.scalar(
        select(Collection).where(Collection.name == body.name)
    )
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe una colección con ese nombre")

    col = Collection(
        name=body.name,
        description=body.description,
        is_active=True,
        created_by=current_user.id,
    )
    db.add(col)
    await db.commit()
    await db.refresh(col)
    return col


@router.get("/{collection_id}", response_model=CollectionOut)
async def get_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(get_current_user),
):
    col = await db.scalar(select(Collection).where(Collection.id == collection_id))
    if not col:
        raise HTTPException(status_code=404, detail="Colección no encontrada")
    return col


@router.put("/{collection_id}", response_model=CollectionOut)
async def update_collection(
    collection_id: uuid.UUID,
    body: CollectionUpdate,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_manage_dep),
):
    col = await db.scalar(select(Collection).where(Collection.id == collection_id))
    if not col:
        raise HTTPException(status_code=404, detail="Colección no encontrada")

    if body.name is not None:
        col.name = body.name
    if body.description is not None:
        col.description = body.description
    if body.is_active is not None:
        col.is_active = body.is_active

    await db.commit()
    await db.refresh(col)
    return col


@router.delete("/{collection_id}")
async def delete_collection(
    collection_id: uuid.UUID,
    action: Literal["auto", "obsolete", "delete"] = Query("auto"),
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_manage_dep),
):
    """
    Elimina una colección.

    - Si la colección no tiene documentos → hard delete inmediato.
    - Si tiene documentos:
      - action="auto" → 409 con conteo, para que el frontend pida decisión.
      - action="obsolete" → documentos pasan a OBSOLETE + collection_id=NULL,
        luego se borra la colección.
      - action="delete" → hard delete de cada documento (archivos, chunks,
        vectores) y luego de la colección.
    """
    col = await db.scalar(select(Collection).where(Collection.id == collection_id))
    if not col:
        raise HTTPException(status_code=404, detail="Colección no encontrada")

    doc_count = await db.scalar(
        select(func.count(PGDocument.id)).where(PGDocument.collection_id == collection_id)
    )
    doc_count = int(doc_count or 0)

    if doc_count == 0:
        await db.delete(col)
        await db.commit()
        return {"deleted": True, "has_documents": False, "document_count": 0}

    if action == "auto":
        raise HTTPException(
            status_code=409,
            detail={
                "has_documents": True,
                "document_count": doc_count,
                "message": "La colección tiene documentos. Indique action=obsolete o action=delete.",
            },
        )

    if action == "obsolete":
        docs_result = await db.execute(
            select(PGDocument).where(PGDocument.collection_id == collection_id)
        )
        for doc in docs_result.scalars():
            doc.status = "OBSOLETE"
            doc.collection_id = None
        await db.flush()
        await db.delete(col)
        await db.commit()
        return {"deleted": True, "has_documents": True, "document_count": doc_count, "obsoleted": doc_count}

    # action == "delete"
    docs_result = await db.execute(
        select(PGDocument.id).where(PGDocument.collection_id == collection_id)
    )
    doc_ids = [row[0] for row in docs_result.all()]
    for doc_id in doc_ids:
        await hard_delete.hard_delete_document(db, doc_id)
    await db.delete(col)
    await db.commit()
    return {"deleted": True, "has_documents": True, "document_count": doc_count, "purged": len(doc_ids)}
