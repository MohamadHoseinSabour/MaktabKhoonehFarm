import uuid

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Section(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'sections'

    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(500))
    title_fa: Mapped[str | None] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    course = relationship('Course', back_populates='sections')
    episodes = relationship('Episode', back_populates='section')
