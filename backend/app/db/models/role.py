import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import PGBase

if TYPE_CHECKING:
    from .user import PGUser


class PGRole(PGBase):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_manage_users: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_manage_collections: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_upload_documents: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_delete_documents: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    users: Mapped[list["PGUser"]] = relationship(
        "PGUser",
        back_populates="role",
        foreign_keys="PGUser.role_id",
    )
