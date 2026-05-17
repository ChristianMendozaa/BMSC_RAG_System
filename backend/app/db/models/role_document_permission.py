import uuid

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import PGBase


class RoleDocumentPermission(PGBase):
    __tablename__ = "role_document_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "document_id", name="uq_role_document"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    can_view: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_download: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_chat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
