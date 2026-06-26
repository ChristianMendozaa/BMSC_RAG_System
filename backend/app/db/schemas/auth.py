import uuid

from pydantic import BaseModel


class LoginRequest(BaseModel):
    identifier: str  # correo para usuarios normales; username para el admin del sistema (is_system=True)
    password: str


class RoleInfo(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_system: bool
    can_manage_users: bool
    can_manage_collections: bool
    can_upload_documents: bool
    can_delete_documents: bool

    model_config = {"from_attributes": True}


class UserInfo(BaseModel):
    id: uuid.UUID
    username: str
    email: str | None = None
    is_active: bool
    role: RoleInfo

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


MeResponse = UserInfo


class SendVerificationCodeRequest(BaseModel):
    identifier: str
    password: str


class VerifyFirstLoginRequest(BaseModel):
    identifier: str
    password: str
    code: str
    new_password: str
