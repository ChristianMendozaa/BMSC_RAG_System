import uuid
from typing import Callable

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.collection_permission import CollectionPermission
from app.db.models.document import PGDocument
from app.db.models.role_document_permission import RoleDocumentPermission
from app.db.models.user import PGUser
from app.db.models.user_collection_permission import UserCollectionPermission
from app.db.models.user_document_permission import UserDocumentPermission
from app.db.session import get_pg_db


def require_permission(permission_name: str) -> Callable:
    """
    Fábrica de dependencias FastAPI.
    Nombres válidos: can_manage_users, can_manage_collections,
                     can_upload_documents, can_delete_documents
    """
    async def _check(
        current_user: PGUser = Depends(_get_current_user_dep()),
    ) -> PGUser:
        has = getattr(current_user.role, permission_name, False)
        if not has:
            raise HTTPException(
                status_code=403,
                detail=f"Permiso requerido: {permission_name}",
            )
        return current_user

    return _check


def _get_current_user_dep():
    from app.dependencies import get_current_user
    return get_current_user


async def get_collection_access(
    user: PGUser,
    collection_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """
    Retorna {can_view, can_download, can_chat}.
    Prioridad: excepción individual de usuario > permiso de rol > todo False.
    """
    ucp = await db.scalar(
        select(UserCollectionPermission).where(
            UserCollectionPermission.user_id == user.id,
            UserCollectionPermission.collection_id == collection_id,
        )
    )
    if ucp:
        return {
            "can_view": ucp.can_view,
            "can_download": ucp.can_download,
            "can_chat": ucp.can_chat,
        }

    cp = await db.scalar(
        select(CollectionPermission).where(
            CollectionPermission.role_id == user.role_id,
            CollectionPermission.collection_id == collection_id,
        )
    )
    if cp:
        return {
            "can_view": cp.can_view,
            "can_download": cp.can_download,
            "can_chat": cp.can_chat,
        }

    return {"can_view": False, "can_download": False, "can_chat": False}


async def get_document_access(
    user: PGUser,
    document_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """
    Retorna {can_view, can_download, can_chat} para un documento específico.

    Orden de resolución (mayor prioridad primero):
    1. user_document_permissions  — override individual de usuario en el documento
    2. role_document_permissions  — permiso del rol del usuario en el documento
    3. user_collection_permissions — override individual en la colección del documento
    4. collection_permissions      — permiso del rol en la colección del documento
    5. Sin acceso por defecto
    """
    no_access = {"can_view": False, "can_download": False, "can_chat": False}

    # 1. Override de usuario en documento específico
    udp = await db.scalar(
        select(UserDocumentPermission).where(
            UserDocumentPermission.user_id == user.id,
            UserDocumentPermission.document_id == document_id,
        )
    )
    if udp is not None:
        return {"can_view": udp.can_view, "can_download": udp.can_download, "can_chat": udp.can_chat}

    # 2. Permiso del rol en documento específico
    rdp = await db.scalar(
        select(RoleDocumentPermission).where(
            RoleDocumentPermission.role_id == user.role_id,
            RoleDocumentPermission.document_id == document_id,
        )
    )
    if rdp is not None:
        return {"can_view": rdp.can_view, "can_download": rdp.can_download, "can_chat": rdp.can_chat}

    # Obtener la colección del documento para los niveles 3 y 4
    doc = await db.scalar(select(PGDocument).where(PGDocument.id == document_id))
    if doc is None:
        return no_access

    # 3. Override de usuario en la colección del documento
    ucp = await db.scalar(
        select(UserCollectionPermission).where(
            UserCollectionPermission.user_id == user.id,
            UserCollectionPermission.collection_id == doc.collection_id,
        )
    )
    if ucp is not None:
        return {"can_view": ucp.can_view, "can_download": ucp.can_download, "can_chat": ucp.can_chat}

    # 4. Permiso del rol en la colección del documento
    cp = await db.scalar(
        select(CollectionPermission).where(
            CollectionPermission.role_id == user.role_id,
            CollectionPermission.collection_id == doc.collection_id,
        )
    )
    if cp is not None:
        return {"can_view": cp.can_view, "can_download": cp.can_download, "can_chat": cp.can_chat}

    return no_access
