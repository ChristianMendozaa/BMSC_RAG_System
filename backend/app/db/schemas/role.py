import uuid
from datetime import datetime

from pydantic import BaseModel


class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    can_manage_users: bool = False
    can_manage_collections: bool = False
    can_upload_documents: bool = False
    can_delete_documents: bool = False


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    can_manage_users: bool | None = None
    can_manage_collections: bool | None = None
    can_upload_documents: bool | None = None
    can_delete_documents: bool | None = None


class RoleOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_system: bool
    can_manage_users: bool
    can_manage_collections: bool
    can_upload_documents: bool
    can_delete_documents: bool
    created_at: datetime

    model_config = {"from_attributes": True}
