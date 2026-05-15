from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import User, Role, Incident
from app.schemas import UserCreate, UserOut, RoleCreate, RoleOut, IncidentCreate, IncidentOut
from app.utils.security import get_password_hash
from app.dependencies import get_current_admin_user

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_current_admin_user)])

@router.get("/roles", response_model=list[RoleOut])
async def get_roles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Role))
    return result.scalars().all()

@router.post("/roles", response_model=RoleOut)
async def create_role(role: RoleCreate, db: AsyncSession = Depends(get_db)):
    db_role = Role(name=role.name)
    db.add(db_role)
    await db.commit()
    await db.refresh(db_role)
    return db_role

@router.get("/users", response_model=list[UserOut])
async def get_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).options(selectinload(User.role)))
    return result.scalars().all()

@router.post("/users", response_model=UserOut)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    hashed_password = get_password_hash(user.password)
    db_user = User(email=user.email, hashed_password=hashed_password, role_id=user.role_id)
    db.add(db_user)
    try:
        await db.commit()
        await db.refresh(db_user)
        # load role
        result = await db.execute(select(User).options(selectinload(User.role)).where(User.id == db_user.id))
        return result.scalar_one()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail="User with this email may already exist")

@router.get("/incidents", response_model=list[IncidentOut])
async def get_incidents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Incident))
    return result.scalars().all()

@router.post("/incidents", response_model=IncidentOut)
async def create_incident(incident: IncidentCreate, db: AsyncSession = Depends(get_db)):
    db_incident = Incident(
        description=incident.description,
        solution=incident.solution,
        resolved_by=incident.resolved_by
    )
    db.add(db_incident)
    await db.commit()
    await db.refresh(db_incident)
    return db_incident
