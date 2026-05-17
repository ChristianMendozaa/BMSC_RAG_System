import uuid

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import PGBase


class UserCollectionPermission(PGBase):
    __tablename__ = "user_collection_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "collection_id", name="uq_user_collection"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    can_view: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_download: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_chat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
