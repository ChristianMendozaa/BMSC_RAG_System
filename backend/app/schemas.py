from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DocumentSummary(BaseModel):
    id: str
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    status: str
    error_message: str | None
    chunk_count: int
    image_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def coerce_uuid(cls, v):
        return str(v)


class ChunkOut(BaseModel):
    id: str
    content: str
    chunk_index: int
    page_number: int | None
    chunk_type: str

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def coerce_uuid(cls, v):
        return str(v)


class DocumentImageOut(BaseModel):
    id: str
    minio_path: str
    page_number: int | None
    image_index: int
    description: str | None

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def coerce_uuid(cls, v):
        return str(v)


class DocumentDetail(DocumentSummary):
    chunks: list[ChunkOut] = []
    images: list[DocumentImageOut] = []


class DocumentStatusOut(BaseModel):
    id: str
    status: str
    error_message: str | None
    chunk_count: int
    image_count: int

    @field_validator("id", mode="before")
    @classmethod
    def coerce_uuid(cls, v):
        return str(v)


class IngestResponse(BaseModel):
    doc_id: str
    filename: str
    status: str


class DocumentsListResponse(BaseModel):
    items: list[DocumentSummary]
    total: int
    skip: int
    limit: int


class Source(BaseModel):
    type: Literal["text", "image"]
    doc_id: str
    filename: str
    page: int | None
    image_id: str | None
    score: float


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None
    collection_id: str | None = None
    document_ids: list[str] | None = None
    mode: Literal["fast", "agentic"] = "fast"


class BlockerItem(BaseModel):
    doc_id: str | None = None
    doc_title_snapshot: str
    reason: str


class ResumeCheckOut(BaseModel):
    can_resume: bool
    blockers: list[BlockerItem]
    collection_id: str | None
    document_ids: list[str]


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    sources: list

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def coerce_uuid(cls, v):
        return str(v)


class ChatSessionUpdate(BaseModel):
    title: str

    @field_validator("title", mode="before")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El título no puede estar vacío")
        return v[:200]


class ChatSessionListItem(BaseModel):
    id: str
    title: str
    collection_id: str | None
    document_ids: list[str]
    updated_at: datetime
    document_count: int

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v):
        return str(v)

    @field_validator("collection_id", mode="before")
    @classmethod
    def coerce_col_id(cls, v):
        return str(v) if v is not None else None

    @field_validator("document_ids", mode="before")
    @classmethod
    def coerce_doc_ids(cls, v):
        return [str(d) for d in (v or [])]


class ChatSessionDetail(BaseModel):
    id: str
    title: str
    collection_id: str | None
    document_ids: list[str]
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageOut]

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v):
        return str(v)

    @field_validator("collection_id", mode="before")
    @classmethod
    def coerce_col_id(cls, v):
        return str(v) if v is not None else None

    @field_validator("document_ids", mode="before")
    @classmethod
    def coerce_doc_ids(cls, v):
        return [str(d) for d in (v or [])]


class HealthService(BaseModel):
    name: str
    status: Literal["ok", "error"]
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    services: list[HealthService]

class RoleCreate(BaseModel):
    name: str

class RoleOut(BaseModel):
    id: str
    name: str
    model_config = {"from_attributes": True}

class UserCreate(BaseModel):
    email: str
    password: str
    role_id: str

class UserOut(BaseModel):
    id: str
    email: str
    role_id: str
    role: RoleOut
    model_config = {"from_attributes": True}

class IncidentCreate(BaseModel):
    description: str
    solution: str
    resolved_by: str

class IncidentOut(BaseModel):
    id: str
    description: str
    solution: str
    resolved_by: str
    created_at: datetime
    model_config = {"from_attributes": True}

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: str | None = None
