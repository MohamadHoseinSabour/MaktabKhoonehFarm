from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

EXPIRED_LINK_ERROR_PREFIX = 'LINK_EXPIRED'
EXPIRED_LINK_USER_MESSAGE = 'Download link has expired. Please provide new links.'
EXPIRED_LINK_ERROR_MESSAGE = f'{EXPIRED_LINK_ERROR_PREFIX}: {EXPIRED_LINK_USER_MESSAGE}'


def is_expired_link_error(exc: Exception, url: str | None = None) -> bool:
    status_code = _extract_status_code(exc)
    message = str(exc).lower()
    tokenized = is_tokenized_download_url(url)

    if status_code in {401, 403, 410} and tokenized:
        return True
    if status_code == 404 and tokenized and ('token' in message or 'hash' in message):
        return True

    expired_hints = (
        'expired',
        'token expired',
        'invalid token',
        'forbidden',
        'signature',
    )
    return tokenized and any(hint in message for hint in expired_hints)


def build_download_error_message(asset_label: str, exc: Exception, url: str | None = None) -> str:
    if is_expired_link_error(exc, url):
        return EXPIRED_LINK_ERROR_MESSAGE
    return f'{asset_label} download failed: {exc}'


def is_tokenized_download_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    return 'token' in query and 'hash' in query


def mark_course_links_expired(course: Any) -> bool:
    metadata = dict(course.extra_metadata or {})
    already_expired = bool(metadata.get('links_expired'))
    metadata['links_expired'] = True
    metadata['links_expired_at'] = datetime.now(timezone.utc).isoformat()
    course.extra_metadata = metadata
    return not already_expired


def clear_course_links_expired(course: Any) -> bool:
    metadata = dict(course.extra_metadata or {})
    changed = False
    for key in ('links_expired', 'links_expired_at'):
        if key in metadata:
            metadata.pop(key, None)
            changed = True
    if changed:
        course.extra_metadata = metadata
    return changed


def _extract_status_code(exc: Exception) -> int | None:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code

    response = getattr(exc, 'response', None)
    if response is not None:
        return getattr(response, 'status_code', None)

    return None
