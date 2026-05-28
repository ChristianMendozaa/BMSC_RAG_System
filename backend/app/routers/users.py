import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.security import get_password_hash
from app.db.models.role import PGRole
from app.db.models.user import PGUser
from app.db.schemas.user import (
    PasswordResetRequest,
    RoleAssignRequest,
    UserCreate,
    UserOut,
    UserUpdate,
    UsernameUpdateRequest,
    UsersListResponse,
)
from app.db.session import get_pg_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=UsersListResponse)
async def list_users(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(get_current_user),
):
    total = await db.scalar(select(func.count()).select_from(PGUser))
    result = await db.execute(
        select(PGUser).offset(skip).limit(limit).order_by(PGUser.created_at.desc())
    )
    users = result.scalars().all()
    return UsersListResponse(items=users, total=total or 0, skip=skip, limit=limit)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(get_current_user),
):
    user = await db.scalar(select(PGUser).where(PGUser.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(require_permission("can_manage_users")),
):
    new_user = PGUser(
        username=body.username,
        hashed_password=get_password_hash(body.password),
        role_id=body.role_id,
        is_active=body.is_active,
        created_by=current_user.id,
    )
    db.add(new_user)
    try:
        await db.commit()
        await db.refresh(new_user)
        user = await db.scalar(select(PGUser).where(PGUser.id == new_user.id))
        return user
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(require_permission("can_manage_users")),
):
    user = await db.scalar(select(PGUser).where(PGUser.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if body.is_active is False and user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")

    if body.is_active is False and user.is_system:
        raise HTTPException(status_code=400, detail="Usuario del sistema, no puede ser desactivado")

    if body.username is not None:
        user.username = body.username
    if body.password is not None:
        user.hashed_password = get_password_hash(body.password)
    if body.role_id is not None:
        user.role_id = body.role_id
    if body.is_active is not None:
        user.is_active = body.is_active

    try:
        await db.commit()
        updated = await db.scalar(select(PGUser).where(PGUser.id == user_id))
        return updated
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")


@router.delete("/{user_id}", status_code=204)
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    current_user: PGUser = Depends(require_permission("can_manage_users")),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")

    user = await db.scalar(select(PGUser).where(PGUser.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.is_system:
        raise HTTPException(status_code=400, detail="Usuario del sistema, no puede ser desactivado")

    if user.role and user.role.name == "SUPERADMIN":
        active_count = await db.scalar(
            select(func.count())
            .select_from(PGUser)
            .join(PGRole, PGUser.role_id == PGRole.id)
            .where(PGRole.name == "SUPERADMIN", PGUser.is_active == True, PGUser.id != user_id)  # noqa: E712
        )
        if not active_count:
            raise HTTPException(status_code=400, detail="No se puede desactivar al único SUPERADMIN activo")

    user.is_active = False
    await db.commit()


@router.post("/{user_id}/activate", response_model=UserOut)
async def activate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(require_permission("can_manage_users")),
):
    """Reactiva un usuario inactivo. Invalida sesiones residuales por precaución."""
    user = await db.scalar(select(PGUser).where(PGUser.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.is_active = True
    user.tokens_valid_after = datetime.now(timezone.utc)
    await db.commit()
    updated = await db.scalar(select(PGUser).where(PGUser.id == user_id))
    return updated


@router.post("/{user_id}/reset-password", status_code=204)
async def reset_user_password(
    user_id: uuid.UUID,
    body: PasswordResetRequest,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(require_permission("can_manage_users")),
):
    """
    Admin resetea la contraseña de un usuario. Setea tokens_valid_after=NOW()
    para invalidar todas las sesiones activas del usuario.
    """
    if not body.new_password or len(body.new_password) < 4:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 4 caracteres")

    user = await db.scalar(select(PGUser).where(PGUser.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.hashed_password = get_password_hash(body.new_password)
    user.tokens_valid_after = datetime.now(timezone.utc)
    await db.commit()


@router.patch("/{user_id}/role", response_model=UserOut)
async def update_user_role(
    user_id: uuid.UUID,
    body: RoleAssignRequest,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(require_permission("can_manage_users")),
):
    """Asigna (o quita) el rol de un usuario. Pensado para usuarios huérfanos."""
    user = await db.scalar(select(PGUser).where(PGUser.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.is_system:
        raise HTTPException(status_code=400, detail="Usuario del sistema, no se puede cambiar el rol")

    if user.role and user.role.name == "SUPERADMIN":
        new_role = await db.scalar(select(PGRole).where(PGRole.id == body.role_id)) if body.role_id else None
        if not new_role or new_role.name != "SUPERADMIN":
            active_count = await db.scalar(
                select(func.count())
                .select_from(PGUser)
                .join(PGRole, PGUser.role_id == PGRole.id)
                .where(PGRole.name == "SUPERADMIN", PGUser.is_active == True, PGUser.id != user_id)  # noqa: E712
            )
            if not active_count:
                raise HTTPException(status_code=400, detail="No se puede dejar el sistema sin un SUPERADMIN activo")

    user.role_id = body.role_id
    await db.commit()
    updated = await db.scalar(select(PGUser).where(PGUser.id == user_id))
    return updated


@router.patch("/{user_id}/username", response_model=UserOut)
async def update_username(
    user_id: uuid.UUID,
    body: UsernameUpdateRequest,
    db: AsyncSession = Depends(get_pg_db),
    _: PGUser = Depends(require_permission("can_manage_users")),
):
    """Cambia el nombre de usuario. Permitido incluso para usuarios del sistema."""
    user = await db.scalar(select(PGUser).where(PGUser.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.username = body.username
    try:
        await db.commit()
        updated = await db.scalar(select(PGUser).where(PGUser.id == user_id))
        return updated
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
