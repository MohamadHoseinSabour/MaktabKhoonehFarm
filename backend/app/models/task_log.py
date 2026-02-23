import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import LogLevel


class TaskLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'task_logs'

    course_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('courses.id', ondelete='SET NULL'))
    episode_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('episodes.id', ondelete='SET NULL'))
    task_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str | None] = mapped_column(String(50))
    message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    level: Mapped[LogLevel] = mapped_column(
        Enum(LogLevel, name='task_log_level', native_enum=False),
        default=LogLevel.INFO,
        nullable=False,
    )