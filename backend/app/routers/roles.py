import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.models.role import PGRole
from app.db.models.user import PGUser
from app.db.schemas.role import RoleCreate, RoleOut, RoleUpdate
from app.db.session import get_pg_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("", response_model=list[RoleOut])
async def list_roles(
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(get_current_user),
):
    result = await db.execute(select(PGRole).order_by(PGRole.name))
    return result.scalars().all()


@router.get("/{role_id}", response_model=RoleOut)
async def get_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(get_current_user),
):
    role = await db.scalar(select(PGRole).where(PGRole.id == role_id))
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    return role


@router.post("", response_model=RoleOut, status_code=201)
async def create_role(
    body: RoleCreate,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(require_permission("can_manage_users")),
):
    role = PGRole(
        name=body.name,
        description=body.description,
        is_system=False,
        can_manage_users=body.can_manage_users,
        can_manage_collections=body.can_manage_collections,
        can_upload_documents=body.can_upload_documents,
        can_delete_documents=body.can_delete_documents,
    )
    db.add(role)
    try:
        await db.commit()
        await db.refresh(role)
        return role
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe un rol con ese nombre")


@router.put("/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(require_permission("can_manage_users")),
):
    role = await db.scalar(select(PGRole).where(PGRole.id == role_id))
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado")

    if role.is_system and (body.name is not None or body.description is not None):
        raise HTTPException(
            status_code=400,
            detail="No se puede cambiar el nombre o descripción de un rol del sistema",
        )

    if body.name is not None:
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    if body.can_manage_users is not None:
        role.can_manage_users = body.can_manage_users
    if body.can_manage_collections is not None:
        role.can_manage_collections = body.can_manage_collections
    if body.can_upload_documents is not None:
        role.can_upload_documents = body.can_upload_documents
    if body.can_delete_documents is not None:
        role.can_delete_documents = body.can_delete_documents

    await db.commit()
    await db.refresh(role)
    return role


@router.delete("/{role_id}", status_code=204)
async def delete_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(require_permission("can_manage_users")),
):
    role = await db.scalar(select(PGRole).where(PGRole.id == role_id))
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado")

    if role.is_system:
        raise HTTPException(status_code=400, detail="Rol del sistema, no eliminable")

    user_count = await db.scalar(
        select(func.count()).select_from(PGUser).where(PGUser.role_id == role_id)
    )
    if user_count and user_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Existen {user_count} usuario(s) con este rol — reasígnalos primero",
        )

    await db.delete(role)
    await db.commit()
