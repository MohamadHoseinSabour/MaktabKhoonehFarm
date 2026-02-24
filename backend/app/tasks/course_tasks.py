import uuid
from datetime import datetime, timezone
from pathlib import Path

from celery import states
from celery.exceptions import Ignore

from app.db.session import SessionLocal
from app.models.course import Course
from app.models.episode import Episode
from app.models.enums import AssetStatus, CourseStatus, LogLevel
from app.services.ai.translator import AITranslator
from app.services.course_service import course_storage_root, scrape_course_metadata
from app.services.downloader.engine import DownloadEngine
from app.services.downloader.file_validator import FileValidator
from app.services.downloader.link_expiry import (
    build_download_error_message,
    is_expired_link_error,
    mark_course_links_expired,
)
from app.services.processor.file_cleaner import clean_filename
from app.services.processor.subtitle_processor import SubtitleProcessor
from app.services.task_logger import log_task_sync
from app.tasks.celery_app import celery_app


def _episode_sort_key(ep: Episode):
    return (ep.episode_number if ep.episode_number is not None else 10**9, ep.sort_order)


def _mark_links_expired_once(db, course: Course, episode: Episode, asset_type: str, url: str | None, exc: Exception) -> None:
    first_time = mark_course_links_expired(course)
    if not first_time:
        return

    log_task_sync(
        db,
        level=LogLevel.WARNING,
        message='Download links have expired. Please provide a fresh link batch in Refresh Links.',
        task_type='links',
        status='expired',
        course_id=course.id,
        episode_id=episode.id,
        details={
            'asset_type': asset_type,
            'url': url,
            'error': str(exc),
        },
    )


@celery_app.task(bind=True, name='app.tasks.scrape_course')
def scrape_course_task(self, course_id: str):
    db = SessionLocal()
    try:
        cid = uuid.UUID(course_id)
        course = db.query(Course).filter(Course.id == cid).first()
        if not course:
            self.update_state(state=states.FAILURE, meta={'reason': 'Course not found'})
            raise Ignore()

        course.status = CourseStatus.SCRAPING
        db.commit()

        scrape_course_metadata(db, course)
        log_task_sync(
            db,
            level=LogLevel.INFO,
            message='Course scraped successfully',
            task_type='scrape',
            status='completed',
            course_id=course.id,
        )
        return {'ok': True, 'course_id': course_id}
    except Exception as exc:
        if 'course' in locals() and course:
            course.status = CourseStatus.ERROR
            db.commit()
            log_task_sync(
                db,
                level=LogLevel.ERROR,
                message=f'Scrape failed: {exc}',
                task_type='scrape',
                status='failed',
                course_id=course.id,
            )
        self.update_state(state=states.FAILURE, meta={'reason': str(exc)})
        raise Ignore() from exc
    finally:
        db.close()


@celery_app.task(bind=True, name='app.tasks.process_course')
def process_course_task(self, course_id: str):
    db = SessionLocal()
    engine = DownloadEngine()
    validator = FileValidator()
    try:
        cid = uuid.UUID(course_id)
        course = db.query(Course).filter(Course.id == cid).first()
        if not course:
            self.update_state(state=states.FAILURE, meta={'reason': 'Course not found'})
            raise Ignore()

        course.status = CourseStatus.DOWNLOADING
        db.commit()

        root = course_storage_root(course)
        episodes = db.query(Episode).filter(Episode.course_id == course.id).all()
        episodes = sorted(episodes, key=_episode_sort_key)

        if course.debug_mode and episodes:
            episodes = episodes[:1]
            log_task_sync(
                db,
                level=LogLevel.DEBUG,
                message='Debug mode enabled: processing first episode only',
                task_type='download',
                status='running',
                course_id=course.id,
            )

        for episode in episodes:
            _download_episode_assets(db, engine, validator, course, episode, root)

        failed_assets = any(
            item in {AssetStatus.ERROR}
            for ep in episodes
            for item in [ep.video_status, ep.subtitle_status, ep.exercise_status]
        )
        course.status = CourseStatus.ERROR if failed_assets else CourseStatus.PROCESSING
        db.commit()
        log_task_sync(
            db,
            level=LogLevel.WARNING if failed_assets else LogLevel.INFO,
            message='Download pipeline finished with errors' if failed_assets else 'Download pipeline finished',
            task_type='download',
            status='failed' if failed_assets else 'completed',
            course_id=course.id,
        )
        return {'ok': True, 'course_id': course_id, 'episodes_processed': len(episodes)}
    except Exception as exc:
        if 'course' in locals() and course:
            course.status = CourseStatus.ERROR
            db.commit()
            log_task_sync(
                db,
                level=LogLevel.ERROR,
                message=f'Download pipeline failed: {exc}',
                task_type='download',
                status='failed',
                course_id=course.id,
            )
        self.update_state(state=states.FAILURE, meta={'reason': str(exc)})
        raise Ignore() from exc
    finally:
        db.close()


@celery_app.task(bind=True, name='app.tasks.process_subtitles')
def process_subtitles_task(self, course_id: str):
    db = SessionLocal()
    processor = SubtitleProcessor()

    try:
        cid = uuid.UUID(course_id)
        course = db.query(Course).filter(Course.id == cid).first()
        if not course:
            self.update_state(state=states.FAILURE, meta={'reason': 'Course not found'})
            raise Ignore()

        root = course_storage_root(course)
        processed = 0

        episodes = db.query(Episode).filter(Episode.course_id == course.id).all()
        for episode in episodes:
            if episode.subtitle_status != AssetStatus.DOWNLOADED:
                continue
            if not episode.subtitle_local_path:
                continue

            src = Path(episode.subtitle_local_path)
            if not src.exists():
                continue

            dst = root / 'subtitles' / 'processed' / f'{src.stem}.vtt'
            episode.subtitle_status = AssetStatus.PROCESSING
            db.commit()

            try:
                processor.process(src, dst)
                episode.subtitle_processed_path = str(dst)
                episode.subtitle_status = AssetStatus.PROCESSED
                processed += 1
            except Exception as exc:
                episode.subtitle_status = AssetStatus.ERROR
                episode.error_message = f'Subtitle processing failed: {exc}'

            db.commit()

        if processed > 0:
            course.status = CourseStatus.READY_FOR_UPLOAD
            db.commit()

        log_task_sync(
            db,
            level=LogLevel.INFO,
            message=f'Processed subtitles: {processed}',
            task_type='process_subtitle',
            status='completed',
            course_id=course.id,
        )
        return {'ok': True, 'processed': processed}
    except Exception as exc:
        self.update_state(state=states.FAILURE, meta={'reason': str(exc)})
        raise Ignore() from exc
    finally:
        db.close()


@celery_app.task(bind=True, name='app.tasks.ai_translate')
def ai_translate_task(self, course_id: str):
    db = SessionLocal()
    try:
        cid = uuid.UUID(course_id)
        course = db.query(Course).filter(Course.id == cid).first()
        if not course:
            self.update_state(state=states.FAILURE, meta={'reason': 'Course not found'})
            raise Ignore()

        translator = AITranslator(db)
        course_result = translator.translate_course(course)
        episodes_result = translator.translate_episode_titles(course)

        log_task_sync(
            db,
            level=LogLevel.INFO,
            message='AI translation finished',
            task_type='ai_translate',
            status='completed',
            course_id=course.id,
            details={'course': course_result, 'episodes': episodes_result},
        )

        return {
            'ok': True,
            'course': course_result,
            'episodes': episodes_result,
        }
    except Exception as exc:
        self.update_state(state=states.FAILURE, meta={'reason': str(exc)})
        raise Ignore() from exc
    finally:
        db.close()


def _download_episode_assets(
    db,
    engine: DownloadEngine,
    validator: FileValidator,
    course: Course,
    episode: Episode,
    root: Path,
) -> None:
    ep_num = episode.episode_number if episode.episode_number is not None else '-'
    if course.debug_mode:
        debug_headers = {'X-Debug-Mode': '1'}
    else:
        debug_headers = None

    if episode.video_download_url and episode.video_status in {AssetStatus.PENDING, AssetStatus.ERROR}:
        log_task_sync(
            db,
            level=LogLevel.INFO,
            message=f'Episode {ep_num}: starting video download',
            task_type='download_video',
            status='running',
            course_id=course.id,
            episode_id=episode.id,
        )
        filename = clean_filename(episode.video_filename or f'{episode.episode_number or 0:03d}-video.mp4')
        target = root / 'videos' / filename
        episode.video_status = AssetStatus.DOWNLOADING
        episode.error_message = None
        episode.last_attempt_at = datetime.now(timezone.utc)
        db.commit()

        try:
            result = engine.download(episode.video_download_url, target, headers=debug_headers)
            episode.video_local_path = str(result.path)
            episode.video_size = result.downloaded_bytes
            episode.video_status = AssetStatus.DOWNLOADED if validator.validate_video(target) else AssetStatus.ERROR
            if episode.video_status == AssetStatus.ERROR:
                episode.error_message = 'Video validation failed after download'
                log_task_sync(
                    db,
                    level=LogLevel.ERROR,
                    message=f'Episode {ep_num}: video validation failed',
                    task_type='download_video',
                    status='failed',
                    course_id=course.id,
                    episode_id=episode.id,
                    details={'path': str(target)},
                )
            else:
                log_task_sync(
                    db,
                    level=LogLevel.INFO,
                    message=f'Episode {ep_num}: video downloaded',
                    task_type='download_video',
                    status='completed',
                    course_id=course.id,
                    episode_id=episode.id,
                    details={'bytes': result.downloaded_bytes},
                )
        except Exception as exc:
            episode.video_status = AssetStatus.ERROR
            expired = is_expired_link_error(exc, episode.video_download_url)
            episode.error_message = build_download_error_message('Video', exc, episode.video_download_url)
            if expired:
                _mark_links_expired_once(db, course, episode, 'video', episode.video_download_url, exc)
            log_task_sync(
                db,
                level=LogLevel.ERROR,
                message=f'Episode {ep_num}: video download failed',
                task_type='download_video',
                status='failed',
                course_id=course.id,
                episode_id=episode.id,
                details={'error': str(exc), 'url': episode.video_download_url, 'expired_link': expired},
            )
        finally:
            episode.retry_count += 1
            db.commit()
    elif episode.video_status in {AssetStatus.PENDING, AssetStatus.ERROR}:
        log_task_sync(
            db,
            level=LogLevel.WARNING,
            message=f'Episode {ep_num}: video URL is missing',
            task_type='download_video',
            status='skipped',
            course_id=course.id,
            episode_id=episode.id,
        )

    if episode.subtitle_download_url and episode.subtitle_status in {AssetStatus.PENDING, AssetStatus.ERROR}:
        log_task_sync(
            db,
            level=LogLevel.INFO,
            message=f'Episode {ep_num}: starting subtitle download',
            task_type='download_subtitle',
            status='running',
            course_id=course.id,
            episode_id=episode.id,
        )
        filename = clean_filename(episode.subtitle_filename or f'{episode.episode_number or 0:03d}-subtitle.srt')
        target = root / 'subtitles' / 'original' / filename
        episode.subtitle_status = AssetStatus.DOWNLOADING
        episode.error_message = None
        episode.last_attempt_at = datetime.now(timezone.utc)
        db.commit()

        try:
            result = engine.download(episode.subtitle_download_url, target, headers=debug_headers)
            episode.subtitle_local_path = str(result.path)
            episode.subtitle_status = AssetStatus.DOWNLOADED if validator.validate_srt(target) else AssetStatus.ERROR
            if episode.subtitle_status == AssetStatus.ERROR:
                episode.error_message = 'Subtitle validation failed after download'
                log_task_sync(
                    db,
                    level=LogLevel.ERROR,
                    message=f'Episode {ep_num}: subtitle validation failed',
                    task_type='download_subtitle',
                    status='failed',
                    course_id=course.id,
                    episode_id=episode.id,
                    details={'path': str(target)},
                )
            else:
                log_task_sync(
                    db,
                    level=LogLevel.INFO,
                    message=f'Episode {ep_num}: subtitle downloaded',
                    task_type='download_subtitle',
                    status='completed',
                    course_id=course.id,
                    episode_id=episode.id,
                    details={'bytes': result.downloaded_bytes},
                )
        except Exception as exc:
            episode.subtitle_status = AssetStatus.ERROR
            expired = is_expired_link_error(exc, episode.subtitle_download_url)
            episode.error_message = build_download_error_message('Subtitle', exc, episode.subtitle_download_url)
            if expired:
                _mark_links_expired_once(db, course, episode, 'subtitle', episode.subtitle_download_url, exc)
            log_task_sync(
                db,
                level=LogLevel.ERROR,
                message=f'Episode {ep_num}: subtitle download failed',
                task_type='download_subtitle',
                status='failed',
                course_id=course.id,
                episode_id=episode.id,
                details={'error': str(exc), 'url': episode.subtitle_download_url, 'expired_link': expired},
            )
        finally:
            episode.retry_count += 1
            db.commit()

    if episode.exercise_download_url and episode.exercise_status in {AssetStatus.PENDING, AssetStatus.ERROR}:
        log_task_sync(
            db,
            level=LogLevel.INFO,
            message=f'Episode {ep_num}: starting exercise download',
            task_type='download_exercise',
            status='running',
            course_id=course.id,
            episode_id=episode.id,
        )
        filename = clean_filename(episode.exercise_filename or f'{episode.episode_number or 0:03d}-exercise.zip')
        target = root / 'exercises' / filename
        episode.exercise_status = AssetStatus.DOWNLOADING
        episode.error_message = None
        episode.last_attempt_at = datetime.now(timezone.utc)
        db.commit()

        try:
            result = engine.download(episode.exercise_download_url, target, headers=debug_headers)
            episode.exercise_local_path = str(result.path)
            episode.exercise_status = AssetStatus.DOWNLOADED
            log_task_sync(
                db,
                level=LogLevel.INFO,
                message=f'Episode {ep_num}: exercise downloaded',
                task_type='download_exercise',
                status='completed',
                course_id=course.id,
                episode_id=episode.id,
                details={'bytes': result.downloaded_bytes},
            )
        except Exception as exc:
            episode.exercise_status = AssetStatus.ERROR
            expired = is_expired_link_error(exc, episode.exercise_download_url)
            episode.error_message = build_download_error_message('Exercise', exc, episode.exercise_download_url)
            if expired:
                _mark_links_expired_once(db, course, episode, 'exercise', episode.exercise_download_url, exc)
            log_task_sync(
                db,
                level=LogLevel.ERROR,
                message=f'Episode {ep_num}: exercise download failed',
                task_type='download_exercise',
                status='failed',
                course_id=course.id,
                episode_id=episode.id,
                details={'error': str(exc), 'url': episode.exercise_download_url, 'expired_link': expired},
            )
        finally:
            episode.retry_count += 1
            db.commit()
