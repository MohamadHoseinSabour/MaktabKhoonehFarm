import uuid
from datetime import datetime

from pydantic import BaseModel, HttpUrl

from app.models.enums import CourseStatus
from app.schemas.common import ORMBaseModel
from app.schemas.episode import EpisodeOut


class CourseCreate(BaseModel):
    source_url: HttpUrl
    debug_mode: bool = False


class CourseUpdate(BaseModel):
    title_en: str | None = None
    title_fa: str | None = None
    description_en: str | None = None
    description_fa: str | None = None
    instructor: str | None = None
    category: str | None = None
    status: CourseStatus | None = None


class CourseOut(ORMBaseModel):
    id: uuid.UUID
    source_url: str
    slug: str | None
    title_en: str | None
    title_fa: str | None
    instructor: str | None
    source_platform: str | None
    lectures_count: int | None
    status: CourseStatus
    debug_mode: bool
    created_at: datetime
    updated_at: datetime


class CourseDetailOut(CourseOut):
    description_en: str | None
    description_fa: str | None
    thumbnail_url: str | None
    thumbnail_local: str | None
    tags: list[str]
    duration: str | None
    level: str | None
    rating: float | None
    students_count: int | None
    language: str | None
    episodes: list[EpisodeOut] = []


class ToggleDebugResponse(BaseModel):
    course_id: uuid.UUID
    debug_mode: bool