import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DownloadLinkBatch(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'download_link_batches'

    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    raw_links: Mapped[str] = mapped_column(Text, nullable=False)
    token: Mapped[str | None] = mapped_column(String(255))
    hash: Mapped[str | None] = mapped_column(String(255))
    course_api_id: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None]

    course = relationship('Course', back_populates='link_batches')