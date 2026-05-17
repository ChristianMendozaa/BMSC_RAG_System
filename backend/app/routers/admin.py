from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db.models.role import PGRole as Role
from app.db.models.user import PGUser as User
from app.db.schemas.role import RoleOut
from app.db.schemas.user import UserOut
from app.db.session import get_pg_db as get_db
from app.dependencies import get_current_admin_user

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin_user)],
)


@router.get("/roles", response_model=list[RoleOut])
async def get_roles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role))
    return result.scalars().all()


@router.get("/users", response_model=list[UserOut])
async def get_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).options(selectinload(User.role)))
    return result.scalars().all()
