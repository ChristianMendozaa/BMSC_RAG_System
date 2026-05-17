import uuid
from datetime import datetime

from pydantic import BaseModel

from app.db.schemas.role import RoleOut


class UserCreate(BaseModel):
    username: str
    password: str
    role_id: uuid.UUID
    is_active: bool = True


class UserUpdate(BaseModel):
    username: str | None = None
    password: str | None = None
    role_id: uuid.UUID | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    is_active: bool
    role_id: uuid.UUID
    role: RoleOut
    created_at: datetime

    model_config = {"from_attributes": True}


class UsersListResponse(BaseModel):
    items: list[UserOut]
    total: int
    skip: int
    limit: int
