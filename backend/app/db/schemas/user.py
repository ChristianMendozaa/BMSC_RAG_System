import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.db.schemas.role import RoleOut


class UserCreate(BaseModel):
    email: EmailStr
    password: str | None = None
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
    email: str | None = None
    is_active: bool
    is_system: bool
    role_id: uuid.UUID | None = None
    role: RoleOut | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PasswordResetRequest(BaseModel):
    new_password: str


class RoleAssignRequest(BaseModel):
    role_id: uuid.UUID | None = None


class EmailUpdateRequest(BaseModel):
    email: EmailStr


class UsersListResponse(BaseModel):
    items: list[UserOut]
    total: int
    skip: int
    limit: int
