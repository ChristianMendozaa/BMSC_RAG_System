import uuid

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import PGBase


class UserDocumentPermission(PGBase):
    __tablename__ = "user_document_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "document_id", name="uq_user_document"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    can_view: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_download: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_chat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
