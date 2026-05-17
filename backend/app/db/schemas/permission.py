import uuid

from pydantic import BaseModel


class PermissionUpdate(BaseModel):
    can_view: bool = False
    can_download: bool = False
    can_chat: bool = False


class CollectionPermissionOut(BaseModel):
    id: uuid.UUID
    role_id: uuid.UUID
    collection_id: uuid.UUID
    can_view: bool
    can_download: bool
    can_chat: bool

    model_config = {"from_attributes": True}


class UserCollectionPermissionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    collection_id: uuid.UUID
    can_view: bool
    can_download: bool
    can_chat: bool

    model_config = {"from_attributes": True}


class RolePermissionEntry(BaseModel):
    role_id: uuid.UUID
    role_name: str
    can_view: bool
    can_download: bool
    can_chat: bool


# --- Permisos a nivel de documento individual ---

class DocumentPermissionUpdate(BaseModel):
    can_view: bool = False
    can_download: bool = False
    can_chat: bool = False


class RoleDocumentPermissionOut(BaseModel):
    id: uuid.UUID
    role_id: uuid.UUID
    role_name: str
    document_id: uuid.UUID
    can_view: bool
    can_download: bool
    can_chat: bool

    model_config = {"from_attributes": True}


class UserDocumentPermissionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    username: str
    document_id: uuid.UUID
    can_view: bool
    can_download: bool
    can_chat: bool

    model_config = {"from_attributes": True}


# --- Colecciones + documentos accesibles para el usuario actual ---

class AccessibleDocumentOut(BaseModel):
    doc_id: uuid.UUID
    title: str
    original_filename: str
    mime_type: str

    model_config = {"from_attributes": True}


class AccessibleCollectionOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    documents: list[AccessibleDocumentOut]

    model_config = {"from_attributes": True}
