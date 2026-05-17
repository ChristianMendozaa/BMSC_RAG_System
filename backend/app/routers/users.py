import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.security import get_password_hash
from app.db.models.user import PGUser
from app.db.schemas.user import UserCreate, UserOut, UserUpdate, UsersListResponse
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

    user.is_active = False
    await db.commit()
