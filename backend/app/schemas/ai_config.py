import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMBaseModel


class AIConfigCreate(BaseModel):
    provider: str
    api_key: str
    model_name: str
    endpoint_url: str | None = None
    is_active: bool = True
    priority: int = 1
    rate_limit: int | None = None
    monthly_budget: float | None = None


class AIConfigUpdate(BaseModel):
    api_key: str | None = None
    model_name: str | None = None
    endpoint_url: str | None = None
    is_active: bool | None = None
    priority: int | None = None
    rate_limit: int | None = None
    monthly_budget: float | None = None


class AIConfigOut(ORMBaseModel):
    id: uuid.UUID
    provider: str
    model_name: str
    endpoint_url: str | None
    is_active: bool
    priority: int
    rate_limit: int | None
    monthly_budget: float | None
    current_month_usage: float
    created_at: datetime
    updated_at: datetime


class AIConfigTestResponse(BaseModel):
    success: bool
    message: str