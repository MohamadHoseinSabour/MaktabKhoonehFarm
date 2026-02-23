import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from slugify import slugify
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.course import Course
from app.models.episode import Episode
from app.models.enums import CourseStatus
from app.services.scraper.gitir_scraper import GitIRScraper

logger = get_logger('service.course')


def ensure_course_slug(course: Course) -> str:
    if course.slug:
        return course.slug

    base = course.title_en or f'course-{str(course.id)[:8]}'
    course.slug = slugify(base, lowercase=True)[:120]
    return course.slug


def course_storage_root(course: Course) -> Path:
    slug = ensure_course_slug(course)
    root = Path(settings.storage_path) / 'courses' / slug
    (root / 'thumbnail').mkdir(parents=True, exist_ok=True)
    (root / 'videos').mkdir(parents=True, exist_ok=True)
    (root / 'subtitles' / 'original').mkdir(parents=True, exist_ok=True)
    (root / 'subtitles' / 'processed').mkdir(parents=True, exist_ok=True)
    (root / 'exercises').mkdir(parents=True, exist_ok=True)
    return root


def scrape_course_metadata(db: Session, course: Course) -> Course:
    scraper = GitIRScraper()
    data = scraper.scrape(course.source_url)

    course.title_en = data.title_en
    course.title_fa = data.title_fa
    course.description_en = data.description_en
    course.description_fa = data.description_fa
    course.instructor = data.instructor
    course.thumbnail_url = data.thumbnail_url
    course.category = data.category
    course.tags = data.tags
    course.duration = data.duration
    course.lectures_count = data.lectures_count
    course.level = data.level
    course.rating = data.rating
    course.students_count = data.students_count
    course.last_updated = data.last_updated
    course.language = data.language
    course.source_platform = data.source_platform
    course.extra_metadata = data.extra_metadata
    course.status = CourseStatus.SCRAPED

    ensure_course_slug(course)
    root = course_storage_root(course)
    thumbnail_local = _download_course_thumbnail(data.thumbnail_url, root)
    if thumbnail_local:
        course.thumbnail_local = thumbnail_local

    existing_numbers = {
        number
        for (number,) in db.query(Episode.episode_number)
        .filter(Episode.course_id == course.id)
        .all()
        if number is not None
    }

    for item in data.episodes:
        number = item.get('episode_number')
        if number in existing_numbers:
            continue
        db.add(
            Episode(
                course_id=course.id,
                episode_number=number,
                title_en=item.get('title_en'),
                sort_order=number or 0,
            )
        )

    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _download_course_thumbnail(url: str | None, root: Path) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)
    extension = Path(parsed.path).suffix.lower()
    if extension not in {'.jpg', '.jpeg', '.png', '.webp'}:
        extension = '.jpg'

    target = root / 'thumbnail' / f'poster{extension}'
    headers = {
        'User-Agent': settings.scraper_user_agent,
        'Accept': 'image/*,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,fa;q=0.8',
    }
    if (parsed.hostname or '').lower().endswith('git.ir'):
        headers['Referer'] = 'https://git.ir/'

    try:
        with httpx.Client(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            target.write_bytes(response.content)
            return str(target)
    except Exception as exc:
        logger.warning('Thumbnail download failed for %s: %s', url, exc)
        return None


def calculate_course_progress(course: Course, episodes: list[Episode]) -> dict:
    total = len(episodes)
    downloaded = len([ep for ep in episodes if ep.video_status.value in {'downloaded', 'processed', 'uploaded'}])
    processed_sub = len([ep for ep in episodes if ep.subtitle_status.value in {'processed', 'uploaded'}])
    failed = len(
        [
            ep
            for ep in episodes
            if 'error' in {ep.video_status.value, ep.subtitle_status.value, ep.exercise_status.value}
        ]
    )
    percent = (downloaded / total * 100.0) if total else 0.0

    return {
        'course_id': str(course.id),
        'total_episodes': total,
        'downloaded_videos': downloaded,
        'processed_subtitles': processed_sub,
        'failed_items': failed,
        'progress_percent': round(percent, 2),
    }


def get_course_or_404(db: Session, course_id: uuid.UUID) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise ValueError('Course not found')
    return course
