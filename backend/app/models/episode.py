import uuid

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AssetStatus


class Episode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'episodes'

    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    section_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('sections.id', ondelete='SET NULL'))

    episode_number: Mapped[int | None] = mapped_column(Integer)
    title_en: Mapped[str | None] = mapped_column(String(500))
    title_fa: Mapped[str | None] = mapped_column(String(500))
    slug: Mapped[str | None] = mapped_column(String(500))
    duration: Mapped[str | None] = mapped_column(String(50))

    video_download_url: Mapped[str | None] = mapped_column(Text)
    video_local_path: Mapped[str | None] = mapped_column(Text)
    video_filename: Mapped[str | None] = mapped_column(Text)
    video_size: Mapped[int | None] = mapped_column(BigInteger)
    video_status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, name='asset_status_video', native_enum=False),
        default=AssetStatus.PENDING,
        nullable=False,
    )

    subtitle_download_url: Mapped[str | None] = mapped_column(Text)
    subtitle_local_path: Mapped[str | None] = mapped_column(Text)
    subtitle_filename: Mapped[str | None] = mapped_column(Text)
    subtitle_status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, name='asset_status_subtitle', native_enum=False),
        default=AssetStatus.PENDING,
        nullable=False,
    )
    subtitle_language: Mapped[str | None] = mapped_column(String(10))
    subtitle_processed_path: Mapped[str | None] = mapped_column(Text)

    exercise_download_url: Mapped[str | None] = mapped_column(Text)
    exercise_local_path: Mapped[str | None] = mapped_column(Text)
    exercise_filename: Mapped[str | None] = mapped_column(Text)
    exercise_status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, name='asset_status_exercise', native_enum=False),
        default=AssetStatus.NOT_AVAILABLE,
        nullable=False,
    )

    hash_code: Mapped[str | None] = mapped_column(String(10))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    course = relationship('Course', back_populates='episodes')
    section = relationship('Section', back_populates='episodes')
    queue_items = relationship('ProcessingQueue', back_populates='episode')
