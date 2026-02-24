import uuid
from urllib.parse import urlparse

import requests

from app.core.cookies import load_scraper_cookies
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.models.course import Course
from app.models.download_link_batch import DownloadLinkBatch
from app.models.episode import Episode
from app.schemas.link import LinkBatchCreate, LinkBatchResult, LinkValidationResult
from app.services.downloader.link_expiry import clear_course_links_expired
from app.services.downloader.link_matcher import LinkMatcher
from app.services.downloader.link_parser import parse_bulk_links

router = APIRouter()


@router.post('/courses/{course_id}/links/', response_model=LinkBatchResult)
def add_or_update_links(course_id: uuid.UUID, payload: LinkBatchCreate, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    _deduplicate_course_episodes(db, course_id)

    parsed = parse_bulk_links(payload.raw_links)
    if not parsed:
        raise HTTPException(status_code=400, detail='No valid links found')

    first = parsed[0]
    batch = DownloadLinkBatch(
        course_id=course_id,
        raw_links=payload.raw_links,
        token=first.token,
        hash=first.hash,
        course_api_id=first.course_api_id,
        is_active=True,
    )

    matcher = LinkMatcher(db)
    result = matcher.apply(course_id=course_id, links=parsed, apply_changes=payload.apply_changes)

    if payload.apply_changes:
        if result.matched > 0 or result.created > 0:
            clear_course_links_expired(course)
        db.add(batch)
        db.commit()
        db.refresh(batch)
        batch_id = batch.id
    else:
        batch_id = None

    return LinkBatchResult(
        batch_id=batch_id,
        matched=result.matched,
        created=result.created,
        unmatched=result.unmatched,
        duplicates=result.duplicates,
        details=result.details,
    )


@router.post('/courses/{course_id}/links/replace/', response_model=LinkBatchResult)
def replace_links(course_id: uuid.UUID, payload: LinkBatchCreate, db: Session = Depends(get_db)):
    return add_or_update_links(course_id, payload, db)


@router.get('/courses/{course_id}/links/')
def get_links(course_id: uuid.UUID, db: Session = Depends(get_db)):
    batches = (
        db.query(DownloadLinkBatch)
        .filter(DownloadLinkBatch.course_id == course_id)
        .order_by(DownloadLinkBatch.created_at.desc())
        .all()
    )
    episodes = db.query(Episode).filter(Episode.course_id == course_id).all()

    return {
        'batches': batches,
        'episode_links': [
            {
                'episode_id': str(ep.id),
                'episode_number': ep.episode_number,
                'video_download_url': ep.video_download_url,
                'subtitle_download_url': ep.subtitle_download_url,
                'exercise_download_url': ep.exercise_download_url,
            }
            for ep in episodes
        ],
    }


@router.post('/courses/{course_id}/links/validate/', response_model=LinkValidationResult)
def validate_links(course_id: uuid.UUID, db: Session = Depends(get_db)):
    episodes = db.query(Episode).filter(Episode.course_id == course_id).all()
    details = []
    valid = 0

    for ep in episodes:
        for file_type, url in [
            ('video', ep.video_download_url),
            ('subtitle', ep.subtitle_download_url),
            ('exercise', ep.exercise_download_url),
        ]:
            if not url:
                continue

            is_valid = _is_url_accessible(url)
            details.append(
                {
                    'episode_id': str(ep.id),
                    'file_type': file_type,
                    'url': url,
                    'valid': is_valid,
                }
            )
            if is_valid:
                valid += 1

    total = len(details)
    return LinkValidationResult(total=total, valid=valid, invalid=total - valid, details=details)


def _is_url_accessible(url: str) -> bool:
    headers = {
        'User-Agent': settings.scraper_user_agent,
        'Accept-Language': 'en-US,en;q=0.9,fa;q=0.8',
    }
    host = (urlparse(url).hostname or '').lower()
    if host.endswith('git.ir'):
        headers['Referer'] = 'https://git.ir/'

    try:
        cookies = load_scraper_cookies()
        response = requests.head(url, timeout=10, allow_redirects=True, headers=headers, cookies=cookies)
        return response.status_code < 400
    except requests.RequestException:
        return False


def _deduplicate_course_episodes(db: Session, course_id: uuid.UUID) -> None:
    episodes = (
        db.query(Episode)
        .filter(Episode.course_id == course_id, Episode.episode_number.isnot(None))
        .order_by(Episode.episode_number.asc(), Episode.created_at.asc())
        .all()
    )
    grouped: dict[tuple[int, str], list[Episode]] = {}
    for ep in episodes:
        key = (ep.episode_number or 0, (ep.title_en or '').strip().lower())
        grouped.setdefault(key, []).append(ep)

    changed = False
    for _key, group in grouped.items():
        if len(group) <= 1:
            continue

        primary = max(
            group,
            key=lambda ep: int(bool(ep.video_download_url)) + int(bool(ep.subtitle_download_url)) + int(bool(ep.exercise_download_url)),
        )
        for candidate in group:
            if candidate.id == primary.id:
                continue

            if not primary.video_download_url and candidate.video_download_url:
                primary.video_download_url = candidate.video_download_url
                primary.video_filename = primary.video_filename or candidate.video_filename
            if not primary.subtitle_download_url and candidate.subtitle_download_url:
                primary.subtitle_download_url = candidate.subtitle_download_url
                primary.subtitle_filename = primary.subtitle_filename or candidate.subtitle_filename
                primary.subtitle_language = primary.subtitle_language or candidate.subtitle_language
            if not primary.exercise_download_url and candidate.exercise_download_url:
                primary.exercise_download_url = candidate.exercise_download_url
                primary.exercise_filename = primary.exercise_filename or candidate.exercise_filename

            db.delete(candidate)
            changed = True

    if changed:
        db.commit()
