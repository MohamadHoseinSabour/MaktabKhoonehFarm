from decimal import Decimal

from sqlalchemy import Boolean, Enum, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CourseStatus


class Course(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'courses'

    source_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    slug: Mapped[str | None] = mapped_column(String(500))
    title_en: Mapped[str | None] = mapped_column(String(500))
    title_fa: Mapped[str | None] = mapped_column(String(500))
    description_en: Mapped[str | None] = mapped_column(Text)
    description_fa: Mapped[str | None] = mapped_column(Text)
    instructor: Mapped[str | None] = mapped_column(String(255))
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_local: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(255))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    duration: Mapped[str | None] = mapped_column(String(100))
    lectures_count: Mapped[int | None] = mapped_column(Integer)
    level: Mapped[str | None] = mapped_column(String(50))
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    students_count: Mapped[int | None] = mapped_column(Integer)
    last_updated: Mapped[str | None] = mapped_column(String(100))
    language: Mapped[str | None] = mapped_column(String(50))
    source_platform: Mapped[str | None] = mapped_column(String(100))
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[CourseStatus] = mapped_column(
        Enum(CourseStatus, name='course_status', native_enum=False),
        default=CourseStatus.SCRAPING,
        nullable=False,
    )
    debug_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    sections = relationship('Section', back_populates='course', cascade='all, delete-orphan')
    episodes = relationship('Episode', back_populates='course', cascade='all, delete-orphan')
    link_batches = relationship('DownloadLinkBatch', back_populates='course', cascade='all, delete-orphan')
    queue_items = relationship('ProcessingQueue', back_populates='course', cascade='all, delete-orphan')