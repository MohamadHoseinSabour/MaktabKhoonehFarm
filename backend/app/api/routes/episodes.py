import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.course import Course
from app.models.episode import Episode
from app.models.enums import AssetStatus, LogLevel
from app.schemas.episode import EpisodeOut, EpisodeUpdate
from app.services.ai.translator import AITranslator
from app.services.course_service import course_storage_root
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
from app.services.upload import (
    FirefoxUploadNavigator,
    UploadAuthExpiredError,
    UploadAutomationError,
    UploadConfigurationError,
)

router = APIRouter()


@router.get('/courses/{course_id}/episodes/', response_model=list[EpisodeOut])
def list_episodes(course_id: uuid.UUID, db: Session = Depends(get_db)):
    return (
        db.query(Episode)
        .filter(Episode.course_id == course_id)
        .order_by(Episode.sort_order.asc(), Episode.episode_number.asc().nullslast())
        .all()
    )


@router.put('/episodes/{episode_id}/', response_model=EpisodeOut)
def update_episode(episode_id: uuid.UUID, payload: EpisodeUpdate, db: Session = Depends(get_db)):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail='Episode not found')

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(episode, key, value)

    db.commit()
    db.refresh(episode)
    return episode


@router.post('/episodes/{episode_id}/retry/')
def retry_episode(episode_id: uuid.UUID, db: Session = Depends(get_db)):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail='Episode not found')

    changed = []
    if episode.video_status == AssetStatus.ERROR:
        episode.video_status = AssetStatus.PENDING
        changed.append('video')
    if episode.subtitle_status == AssetStatus.ERROR:
        episode.subtitle_status = AssetStatus.PENDING
        changed.append('subtitle')
    if episode.exercise_status == AssetStatus.ERROR:
        episode.exercise_status = AssetStatus.PENDING
        changed.append('exercise')

    db.commit()
    return {'episode_id': str(episode.id), 'reset': changed}


@router.post('/episodes/{episode_id}/download/')
def download_episode_assets(episode_id: uuid.UUID, db: Session = Depends(get_db)):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail='Episode not found')

    course = db.query(Course).filter(Course.id == episode.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    root = course_storage_root(course)
    engine = DownloadEngine()
    validator = FileValidator()

    result = _download_episode_assets(db, course, episode, root, engine, validator)
    return {'episode_id': str(episode.id), 'result': result}


@router.post('/episodes/{episode_id}/process/')
def process_episode_assets(episode_id: uuid.UUID, db: Session = Depends(get_db)):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail='Episode not found')

    course = db.query(Course).filter(Course.id == episode.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    root = course_storage_root(course)
    processor = SubtitleProcessor()
    changes: list[str] = []

    if episode.subtitle_local_path and Path(episode.subtitle_local_path).exists():
        src = Path(episode.subtitle_local_path)
        dst = root / 'subtitles' / 'processed' / f'{src.stem}.vtt'
        episode.subtitle_status = AssetStatus.PROCESSING
        db.commit()
        try:
            processor.process(src, dst)
            episode.subtitle_processed_path = str(dst)
            episode.subtitle_status = AssetStatus.PROCESSED
            changes.append('subtitle')
        except Exception as exc:
            episode.subtitle_status = AssetStatus.ERROR
            episode.error_message = f'Subtitle processing failed: {exc}'
        db.commit()

    if episode.video_status == AssetStatus.DOWNLOADED:
        episode.video_status = AssetStatus.PROCESSED
        changes.append('video')
        db.commit()

    if episode.exercise_status == AssetStatus.DOWNLOADED:
        episode.exercise_status = AssetStatus.PROCESSED
        changes.append('exercise')
        db.commit()

    log_task_sync(
        db,
        level=LogLevel.INFO,
        message=f'Episode processed ({episode.episode_number})',
        task_type='process_episode',
        status='completed',
        course_id=course.id,
        episode_id=episode.id,
        details={'changes': changes},
    )

    return {'episode_id': str(episode.id), 'processed': changes}


@router.post('/episodes/{episode_id}/upload/')
def upload_episode_assets(episode_id: uuid.UUID, db: Session = Depends(get_db)):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail='Episode not found')

    course = db.query(Course).filter(Course.id == episode.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    ordered_episodes = (
        db.query(Episode)
        .filter(Episode.course_id == course.id)
        .order_by(Episode.sort_order.asc(), Episode.episode_number.asc().nullslast())
        .all()
    )
    start_index = next((idx for idx, item in enumerate(ordered_episodes) if item.id == episode.id), None)
    if start_index is None:
        raise HTTPException(status_code=404, detail='Episode not found in ordered list')

    target_episodes = ordered_episodes[start_index:]
    if course.debug_mode and target_episodes:
        target_episodes = target_episodes[:1]

    try:
        navigator = FirefoxUploadNavigator(db)
        metadata = dict(course.extra_metadata or {})
        preferred_units_url = metadata.get('upload_units_url') if isinstance(metadata.get('upload_units_url'), str) else None
        navigation = navigator.upload_course_episodes(
            course,
            target_episodes,
            keep_browser_open=bool(course.debug_mode),
            preferred_units_url=preferred_units_url,
        )
        units_list_url = navigation.get('units_list_url')
        if isinstance(units_list_url, str) and units_list_url:
            if metadata.get('upload_units_url') != units_list_url:
                metadata['upload_units_url'] = units_list_url
                course.extra_metadata = metadata
                db.commit()
    except UploadAuthExpiredError as exc:
        log_task_sync(
            db,
            level=LogLevel.WARNING,
            message='Upload session cookies expired or invalid',
            task_type='upload_navigation',
            status='failed',
            course_id=course.id,
            episode_id=episode.id,
            details={'error': str(exc)},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UploadConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UploadAutomationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    episode_map = {str(item.id): item for item in ordered_episodes}
    run_results = navigation.get('results') if isinstance(navigation.get('results'), list) else []
    run_uploaded = 0
    run_failed = 0
    run_skipped_existing = 0
    uploaded_episode_ids: list[str] = []

    for row in run_results:
        if not isinstance(row, dict):
            continue
        row_episode_id = str(row.get('episode_id') or '')
        current_episode = episode_map.get(row_episode_id)
        if current_episode is None:
            continue

        result = str(row.get('result') or '')
        if result == 'uploaded':
            run_uploaded += 1
            uploaded_episode_ids.append(row_episode_id)
            current_episode.video_status = AssetStatus.UPLOADED
            if bool(row.get('subtitle_attached')):
                current_episode.subtitle_status = AssetStatus.UPLOADED
            current_episode.error_message = None
            continue

        if result == 'skipped_existing':
            run_skipped_existing += 1
            continue

        run_failed += 1
        current_episode.video_status = AssetStatus.ERROR
        if result == 'skipped_missing_video':
            current_episode.error_message = 'Upload skipped: local video file is missing.'
        else:
            error_text = str(row.get('error') or 'Upload automation failed.')
            current_episode.error_message = f'Upload failed: {error_text}'

    uploaded_total = sum(1 for item in ordered_episodes if item.video_status == AssetStatus.UPLOADED)
    failed_total = sum(1 for item in ordered_episodes if item.video_status == AssetStatus.ERROR)
    requested_count = len(target_episodes)
    processed_count = len(run_results)
    run_state = 'failed' if run_failed > 0 and run_uploaded == 0 else ('partial_error' if run_failed > 0 else 'completed')

    summary = {
        'state': run_state,
        'run_requested': requested_count,
        'run_processed': processed_count,
        'run_uploaded': run_uploaded,
        'run_failed': run_failed,
        'run_skipped_existing': run_skipped_existing,
        'uploaded_total': uploaded_total,
        'failed_total': failed_total,
        'total_episodes': len(ordered_episodes),
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    metadata = dict(course.extra_metadata or {})
    metadata['upload_summary'] = summary
    course.extra_metadata = metadata
    db.commit()

    first_result = run_results[0] if run_results and isinstance(run_results[0], dict) else {}
    first_skip_existing = bool(first_result.get('result') == 'skipped_existing')
    debug_halt = bool(course.debug_mode and first_skip_existing)

    log_status = 'failed' if run_failed > 0 else ('skipped' if run_uploaded == 0 and run_skipped_existing > 0 else 'completed')
    log_message = (
        f'Upload automation finished: uploaded={run_uploaded}, failed={run_failed}, skipped={run_skipped_existing}'
    )

    log_task_sync(
        db,
        level=LogLevel.WARNING if run_failed > 0 else LogLevel.INFO,
        message=log_message,
        task_type='upload_navigation',
        status=log_status,
        course_id=course.id,
        episode_id=episode.id,
        details=navigation,
    )
    return {
        'episode_id': str(episode.id),
        'uploaded': uploaded_episode_ids,
        'navigation': navigation,
        'status': log_status,
        'skip_existing': first_skip_existing,
        'debug_halt': debug_halt,
        'summary': summary,
    }


@router.post('/episodes/{episode_id}/translate-title/', response_model=EpisodeOut)
def translate_episode_title(episode_id: uuid.UUID, db: Session = Depends(get_db)):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail='Episode not found')

    course = db.query(Course).filter(Course.id == episode.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')
    if not episode.title_en:
        raise HTTPException(status_code=400, detail='Episode English title is empty')

    translator = AITranslator(db)
    result = translator.translate_episode_title(course, episode)
    if not result.get('translated'):
        raise HTTPException(status_code=400, detail=result.get('reason', 'Translation failed'))

    db.refresh(episode)
    log_task_sync(
        db,
        level=LogLevel.INFO,
        message=f'Episode title translated ({episode.episode_number})',
        task_type='translate_episode_title',
        status='completed',
        course_id=course.id,
        episode_id=episode.id,
    )
    return episode


def _download_episode_assets(
    db: Session,
    course: Course,
    episode: Episode,
    root: Path,
    engine: DownloadEngine,
    validator: FileValidator,
) -> dict:
    result: dict[str, str] = {}

    if episode.video_download_url:
        filename = clean_filename(episode.video_filename or f'{episode.episode_number or 0:03d}-video.mp4')
        target = root / 'videos' / filename
        episode.video_status = AssetStatus.DOWNLOADING
        episode.error_message = None
        episode.last_attempt_at = datetime.now(timezone.utc)
        db.commit()
        try:
            download_result = engine.download(episode.video_download_url, target)
            episode.video_local_path = str(download_result.path)
            episode.video_size = download_result.downloaded_bytes
            episode.video_status = AssetStatus.DOWNLOADED if validator.validate_video(target) else AssetStatus.ERROR
            result['video'] = episode.video_status.value
        except Exception as exc:
            episode.video_status = AssetStatus.ERROR
            expired = is_expired_link_error(exc, episode.video_download_url)
            episode.error_message = build_download_error_message('Video', exc, episode.video_download_url)
            if expired:
                first_time = mark_course_links_expired(course)
                if first_time:
                    log_task_sync(
                        db,
                        level=LogLevel.WARNING,
                        message='Download links have expired. Please provide a fresh link batch in Refresh Links.',
                        task_type='links',
                        status='expired',
                        course_id=course.id,
                        episode_id=episode.id,
                        details={'asset_type': 'video', 'url': episode.video_download_url, 'error': str(exc)},
                    )
            result['video'] = 'error'
        finally:
            episode.retry_count += 1
            db.commit()

    if episode.subtitle_download_url:
        filename = clean_filename(episode.subtitle_filename or f'{episode.episode_number or 0:03d}-subtitle.srt')
        target = root / 'subtitles' / 'original' / filename
        episode.subtitle_status = AssetStatus.DOWNLOADING
        episode.error_message = None
        episode.last_attempt_at = datetime.now(timezone.utc)
        db.commit()
        try:
            download_result = engine.download(episode.subtitle_download_url, target)
            episode.subtitle_local_path = str(download_result.path)
            episode.subtitle_status = AssetStatus.DOWNLOADED if validator.validate_srt(target) else AssetStatus.ERROR
            result['subtitle'] = episode.subtitle_status.value
        except Exception as exc:
            episode.subtitle_status = AssetStatus.ERROR
            expired = is_expired_link_error(exc, episode.subtitle_download_url)
            episode.error_message = build_download_error_message('Subtitle', exc, episode.subtitle_download_url)
            if expired:
                first_time = mark_course_links_expired(course)
                if first_time:
                    log_task_sync(
                        db,
                        level=LogLevel.WARNING,
                        message='Download links have expired. Please provide a fresh link batch in Refresh Links.',
                        task_type='links',
                        status='expired',
                        course_id=course.id,
                        episode_id=episode.id,
                        details={'asset_type': 'subtitle', 'url': episode.subtitle_download_url, 'error': str(exc)},
                    )
            result['subtitle'] = 'error'
        finally:
            episode.retry_count += 1
            db.commit()

    if episode.exercise_download_url:
        filename = clean_filename(episode.exercise_filename or f'{episode.episode_number or 0:03d}-exercise.zip')
        target = root / 'exercises' / filename
        episode.exercise_status = AssetStatus.DOWNLOADING
        episode.error_message = None
        episode.last_attempt_at = datetime.now(timezone.utc)
        db.commit()
        try:
            download_result = engine.download(episode.exercise_download_url, target)
            episode.exercise_local_path = str(download_result.path)
            episode.exercise_status = AssetStatus.DOWNLOADED
            result['exercise'] = episode.exercise_status.value
        except Exception as exc:
            episode.exercise_status = AssetStatus.ERROR
            expired = is_expired_link_error(exc, episode.exercise_download_url)
            episode.error_message = build_download_error_message('Exercise', exc, episode.exercise_download_url)
            if expired:
                first_time = mark_course_links_expired(course)
                if first_time:
                    log_task_sync(
                        db,
                        level=LogLevel.WARNING,
                        message='Download links have expired. Please provide a fresh link batch in Refresh Links.',
                        task_type='links',
                        status='expired',
                        course_id=course.id,
                        episode_id=episode.id,
                        details={'asset_type': 'exercise', 'url': episode.exercise_download_url, 'error': str(exc)},
                    )
            result['exercise'] = 'error'
        finally:
            episode.retry_count += 1
            db.commit()

    return result
