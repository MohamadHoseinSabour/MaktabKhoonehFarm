import uuid
from datetime import datetime
import re
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.models.enums import CourseStatus
from app.schemas.common import ORMBaseModel
from app.schemas.episode import EpisodeOut

URL_SCHEME_RE = re.compile(r'https?://', re.IGNORECASE)


def normalize_course_source_url(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return normalized

    occurrences = list(URL_SCHEME_RE.finditer(normalized))
    if len(occurrences) > 1:
        second_start = occurrences[1].start()
        first_url = normalized[:second_start]
        trailing = normalized[second_start:]
        if trailing.rstrip('/') == first_url.rstrip('/'):
            normalized = first_url
        else:
            raise ValueError('Invalid source URL: multiple URL segments detected. Paste a single course URL.')

    parsed = urlsplit(normalized)
    if parsed.fragment:
        normalized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))

    return normalized


class CourseCreate(BaseModel):
    source_url: HttpUrl
    debug_mode: bool = True

    @field_validator('source_url', mode='before')
    @classmethod
    def validate_source_url(cls, value):
        if isinstance(value, str):
            return normalize_course_source_url(value)
        return value


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
    description_en: str | None
    description_fa: str | None
    thumbnail_url: str | None
    thumbnail_local: str | None
    instructor: str | None
    source_platform: str | None
    lectures_count: int | None
    extra_metadata: dict[str, object] = Field(default_factory=dict)
    status: CourseStatus
    debug_mode: bool
    created_at: datetime
    updated_at: datetime


class CourseDetailOut(CourseOut):
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
