import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ProcessingTaskType, QueueStatus


class ProcessingQueue(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'processing_queue'

    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    episode_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('episodes.id', ondelete='SET NULL'))
    task_type: Mapped[ProcessingTaskType] = mapped_column(
        Enum(ProcessingTaskType, name='processing_task_type', native_enum=False),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    status: Mapped[QueueStatus] = mapped_column(
        Enum(QueueStatus, name='processing_queue_status', native_enum=False),
        default=QueueStatus.QUEUED,
        nullable=False,
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    scheduled_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    error_message: Mapped[str | None] = mapped_column(Text)

    course = relationship('Course', back_populates='queue_items')
    episode = relationship('Episode', back_populates='queue_items')