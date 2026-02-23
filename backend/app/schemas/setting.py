import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMBaseModel


class SettingIn(BaseModel):
    key: str
    value: str
    category: str | None = None
    description: str | None = None


class SettingOut(ORMBaseModel):
    id: uuid.UUID
    key: str
    value: str
    category: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime