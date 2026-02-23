from pathlib import Path

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if (BACKEND_ROOT.parent / 'backend').exists() and (BACKEND_ROOT.parent / 'frontend').exists():
    PROJECT_ROOT = BACKEND_ROOT.parent
else:
    PROJECT_ROOT = BACKEND_ROOT


def default_storage_path() -> str:
    return str((PROJECT_ROOT / 'storage').resolve())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', case_sensitive=False, extra='ignore')

    app_name: str = 'ACMS'
    api_v1_prefix: str = '/api'
    debug: bool = False
    log_level: str = 'INFO'

    database_url: str = 'postgresql+psycopg://acms:password@db:5432/acms_db'
    redis_url: str = 'redis://redis:6379/0'
    secret_key: str = Field(default='change-me', min_length=8)
    allowed_hosts: str = 'localhost,127.0.0.1'

    storage_path: str = Field(default_factory=default_storage_path)
    max_storage_gb: int = 500

    max_concurrent_downloads: int = 3
    download_speed_limit_kb: int = 0
    download_retry_attempts: int = 3
    download_retry_backoff_seconds: int = 2
    request_timeout_seconds: int = 30

    scraper_user_agent: str = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36'
    )
    scraper_request_delay_seconds: float = 1.0

    openai_api_key: str | None = None
    openai_model: str = 'gpt-4o-mini'
    claude_api_key: str | None = None
    claude_model: str = 'claude-3-5-sonnet-20241022'
    ai_batch_size: int = 20

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    next_public_api_base_url: str = 'http://localhost:8000'

    @field_validator('storage_path')
    @classmethod
    def resolve_storage_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute():
            return str(path)
        return str((PROJECT_ROOT / path).resolve())


settings = Settings()
