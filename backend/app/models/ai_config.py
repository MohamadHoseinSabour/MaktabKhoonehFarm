from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AIConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'ai_configs'

    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    endpoint_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    rate_limit: Mapped[int | None] = mapped_column(Integer)
    monthly_budget: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    current_month_usage: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)