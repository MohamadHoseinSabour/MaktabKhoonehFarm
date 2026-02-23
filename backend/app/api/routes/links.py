import uuid

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.course import Course
from app.models.download_link_batch import DownloadLinkBatch
from app.models.episode import Episode
from app.schemas.link import LinkBatchCreate, LinkBatchResult, LinkValidationResult
from app.services.downloader.link_matcher import LinkMatcher
from app.services.downloader.link_parser import parse_bulk_links

router = APIRouter()


@router.post('/courses/{course_id}/links/', response_model=LinkBatchResult)
def add_or_update_links(course_id: uuid.UUID, payload: LinkBatchCreate, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

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
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        return response.status_code < 400
    except requests.RequestException:
        return False