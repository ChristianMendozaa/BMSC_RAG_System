import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.models.collection import Collection
from app.db.models.collection_permission import CollectionPermission
from app.db.models.document import PGDocument
from app.db.models.role import PGRole
from app.db.models.role_document_permission import RoleDocumentPermission
from app.db.models.user import PGUser
from app.db.models.user_collection_permission import UserCollectionPermission
from app.db.models.user_document_permission import UserDocumentPermission
from app.db.schemas.permission import (
    CollectionPermissionOut,
    DocumentPermissionUpdate,
    PermissionUpdate,
    RoleDocumentPermissionOut,
    RolePermissionEntry,
    UserCollectionPermissionOut,
    UserDocumentPermissionOut,
)
from app.db.session import get_pg_db

router = APIRouter(
    prefix="/api/collections/{collection_id}/permissions",
    tags=["permissions"],
)

doc_perm_router = APIRouter(
    prefix="/api/documents/{document_id}/permissions",
    tags=["document-permissions"],
)

_perm_dep = require_permission("can_manage_collections")


async def _get_collection(collection_id: uuid.UUID, db: AsyncSession) -> Collection:
    col = await db.scalar(select(Collection).where(Collection.id == collection_id))
    if not col:
        raise HTTPException(status_code=404, detail="Colección no encontrada")
    return col


@router.get("/roles", response_model=list[RolePermissionEntry])
async def list_role_permissions(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_perm_dep),
):
    await _get_collection(collection_id, db)

    roles_result = await db.execute(select(PGRole))
    roles = roles_result.scalars().all()

    perms_result = await db.execute(
        select(CollectionPermission).where(
            CollectionPermission.collection_id == collection_id
        )
    )
    perms = {p.role_id: p for p in perms_result.scalars().all()}

    entries = []
    for role in roles:
        p = perms.get(role.id)
        entries.append(
            RolePermissionEntry(
                role_id=role.id,
                role_name=role.name,
                can_view=p.can_view if p else False,
                can_download=p.can_download if p else False,
                can_chat=p.can_chat if p else False,
            )
        )
    return entries


@router.put("/roles/{role_id}", response_model=CollectionPermissionOut)
async def upsert_role_permission(
    collection_id: uuid.UUID,
    role_id: uuid.UUID,
    body: PermissionUpdate,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_perm_dep),
):
    await _get_collection(collection_id, db)

    perm = await db.scalar(
        select(CollectionPermission).where(
            CollectionPermission.role_id == role_id,
            CollectionPermission.collection_id == collection_id,
        )
    )
    if perm:
        perm.can_view = body.can_view
        perm.can_download = body.can_download
        perm.can_chat = body.can_chat
    else:
        perm = CollectionPermission(
            role_id=role_id,
            collection_id=collection_id,
            can_view=body.can_view,
            can_download=body.can_download,
            can_chat=body.can_chat,
        )
        db.add(perm)

    await db.commit()
    await db.refresh(perm)
    return perm


@router.get("/users", response_model=list[UserCollectionPermissionOut])
async def list_user_permissions(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_perm_dep),
):
    await _get_collection(collection_id, db)
    result = await db.execute(
        select(UserCollectionPermission).where(
            UserCollectionPermission.collection_id == collection_id
        )
    )
    return result.scalars().all()


@router.put("/users/{user_id}", response_model=UserCollectionPermissionOut)
async def upsert_user_permission(
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
    body: PermissionUpdate,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_perm_dep),
):
    await _get_collection(collection_id, db)

    perm = await db.scalar(
        select(UserCollectionPermission).where(
            UserCollectionPermission.user_id == user_id,
            UserCollectionPermission.collection_id == collection_id,
        )
    )
    if perm:
        perm.can_view = body.can_view
        perm.can_download = body.can_download
        perm.can_chat = body.can_chat
    else:
        perm = UserCollectionPermission(
            user_id=user_id,
            collection_id=collection_id,
            can_view=body.can_view,
            can_download=body.can_download,
            can_chat=body.can_chat,
        )
        db.add(perm)

    await db.commit()
    await db.refresh(perm)
    return perm


@router.delete("/users/{user_id}", status_code=204)
async def delete_user_permission(
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_perm_dep),
):
    perm = await db.scalar(
        select(UserCollectionPermission).where(
            UserCollectionPermission.user_id == user_id,
            UserCollectionPermission.collection_id == collection_id,
        )
    )
    if not perm:
        raise HTTPException(
            status_code=404,
            detail="Excepción de usuario no encontrada para esta colección",
        )
    await db.delete(perm)
    await db.commit()


# ============================================================
#  Permisos a nivel de documento individual
# ============================================================

async def _get_document(document_id: uuid.UUID, db: AsyncSession) -> PGDocument:
    doc = await db.scalar(select(PGDocument).where(PGDocument.id == document_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return doc


@doc_perm_router.get("/roles", response_model=list[RoleDocumentPermissionOut])
async def list_role_document_permissions(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_perm_dep),
):
    await _get_document(document_id, db)

    roles_result = await db.execute(select(PGRole))
    roles = roles_result.scalars().all()

    perms_result = await db.execute(
        select(RoleDocumentPermission).where(
            RoleDocumentPermission.document_id == document_id
        )
    )
    perms = {p.role_id: p for p in perms_result.scalars().all()}

    entries = []
    for role in roles:
        p = perms.get(role.id)
        entries.append(
            RoleDocumentPermissionOut(
                id=p.id if p else uuid.uuid4(),
                role_id=role.id,
                role_name=role.name,
                document_id=document_id,
                can_view=p.can_view if p else False,
                can_download=p.can_download if p else False,
                can_chat=p.can_chat if p else False,
            )
        )
    return entries


@doc_perm_router.put("/roles/{role_id}", response_model=RoleDocumentPermissionOut)
async def upsert_role_document_permission(
    document_id: uuid.UUID,
    role_id: uuid.UUID,
    body: DocumentPermissionUpdate,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_perm_dep),
):
    await _get_document(document_id, db)

    perm = await db.scalar(
        select(RoleDocumentPermission).where(
            RoleDocumentPermission.role_id == role_id,
            RoleDocumentPermission.document_id == document_id,
        )
    )
    if perm:
        perm.can_view = body.can_view
        perm.can_download = body.can_download
        perm.can_chat = body.can_chat
    else:
        perm = RoleDocumentPermission(
            role_id=role_id,
            document_id=document_id,
            can_view=body.can_view,
            can_download=body.can_download,
            can_chat=body.can_chat,
        )
        db.add(perm)

    await db.commit()
    await db.refresh(perm)

    role = await db.scalar(select(PGRole).where(PGRole.id == role_id))
    return RoleDocumentPermissionOut(
        id=perm.id,
        role_id=perm.role_id,
        role_name=role.name if role else "",
        document_id=perm.document_id,
        can_view=perm.can_view,
        can_download=perm.can_download,
        can_chat=perm.can_chat,
    )


@doc_perm_router.delete("/roles/{role_id}", status_code=204)
async def delete_role_document_permission(
    document_id: uuid.UUID,
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_perm_dep),
):
    perm = await db.scalar(
        select(RoleDocumentPermission).where(
            RoleDocumentPermission.role_id == role_id,
            RoleDocumentPermission.document_id == document_id,
        )
    )
    if not perm:
        raise HTTPException(status_code=404, detail="Permiso de rol no encontrado para este documento")
    await db.delete(perm)
    await db.commit()


@doc_perm_router.get("/users", response_model=list[UserDocumentPermissionOut])
async def list_user_document_permissions(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_perm_dep),
):
    await _get_document(document_id, db)
    result = await db.execute(
        select(UserDocumentPermission, PGUser)
        .join(PGUser, PGUser.id == UserDocumentPermission.user_id)
        .where(UserDocumentPermission.document_id == document_id)
    )
    rows = result.all()
    return [
        UserDocumentPermissionOut(
            id=udp.id,
            user_id=udp.user_id,
            username=user.username,
            document_id=udp.document_id,
            can_view=udp.can_view,
            can_download=udp.can_download,
            can_chat=udp.can_chat,
        )
        for udp, user in rows
    ]


@doc_perm_router.put("/users/{user_id}", response_model=UserDocumentPermissionOut)
async def upsert_user_document_permission(
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    body: DocumentPermissionUpdate,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_perm_dep),
):
    await _get_document(document_id, db)

    perm = await db.scalar(
        select(UserDocumentPermission).where(
            UserDocumentPermission.user_id == user_id,
            UserDocumentPermission.document_id == document_id,
        )
    )
    if perm:
        perm.can_view = body.can_view
        perm.can_download = body.can_download
        perm.can_chat = body.can_chat
    else:
        perm = UserDocumentPermission(
            user_id=user_id,
            document_id=document_id,
            can_view=body.can_view,
            can_download=body.can_download,
            can_chat=body.can_chat,
        )
        db.add(perm)

    await db.commit()
    await db.refresh(perm)

    user = await db.scalar(select(PGUser).where(PGUser.id == user_id))
    return UserDocumentPermissionOut(
        id=perm.id,
        user_id=perm.user_id,
        username=user.username if user else "",
        document_id=perm.document_id,
        can_view=perm.can_view,
        can_download=perm.can_download,
        can_chat=perm.can_chat,
    )


@doc_perm_router.delete("/users/{user_id}", status_code=204)
async def delete_user_document_permission(
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(_perm_dep),
):
    perm = await db.scalar(
        select(UserDocumentPermission).where(
            UserDocumentPermission.user_id == user_id,
            UserDocumentPermission.document_id == document_id,
        )
    )
    if not perm:
        raise HTTPException(status_code=404, detail="Excepción de usuario no encontrada para este documento")
    await db.delete(perm)
    await db.commit()
