import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import AssetStatus
from app.schemas.common import ORMBaseModel


class EpisodeUpdate(BaseModel):
    title_en: str | None = None
    title_fa: str | None = None
    slug: str | None = None
    video_download_url: str | None = None
    subtitle_download_url: str | None = None
    exercise_download_url: str | None = None


class EpisodeOut(ORMBaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    section_id: uuid.UUID | None
    episode_number: int | None
    title_en: str | None
    title_fa: str | None
    slug: str | None
    duration: str | None
    video_download_url: str | None
    video_local_path: str | None
    video_status: AssetStatus
    subtitle_download_url: str | None
    subtitle_local_path: str | None
    subtitle_status: AssetStatus
    exercise_download_url: str | None
    exercise_local_path: str | None
    exercise_status: AssetStatus
    video_filename: str | None
    subtitle_filename: str | None
    exercise_filename: str | None
    subtitle_processed_path: str | None
    hash_code: str | None
    sort_order: int
    error_message: str | None
    retry_count: int
    last_attempt_at: datetime | None
    created_at: datetime
    updated_at: datetime
