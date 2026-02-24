"""Shared cookie helpers for scraper / downloader requests."""

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.setting import Setting

logger = logging.getLogger('core.cookies')

SETTING_KEY = 'scraper_cookies_json'


def _load_raw(db: Session | None = None) -> str:
    """Return the raw JSON string stored under *scraper_cookies_json*."""
    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        row = db.query(Setting).filter(Setting.key == SETTING_KEY).first()
        return row.value if row else '[]'
    finally:
        if close:
            db.close()


def load_scraper_cookies(db: Session | None = None) -> dict[str, str]:
    """Return a ``{name: value}`` dict ready for ``httpx`` / ``requests``."""
    raw = _load_raw(db)
    try:
        items: list[dict[str, Any]] = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(items, list):
        return {}
    return {
        str(c['name']): str(c['value'])
        for c in items
        if isinstance(c, dict) and c.get('name') and c.get('value')
    }
