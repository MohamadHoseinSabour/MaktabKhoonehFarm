import uuid
from datetime import datetime

from app.models.enums import LogLevel
from app.schemas.common import ORMBaseModel


class TaskLogOut(ORMBaseModel):
    id: uuid.UUID
    course_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    task_type: str | None
    status: str | None
    message: str | None
    details: dict
    level: LogLevel
    created_at: datetime
    updated_at: datetime