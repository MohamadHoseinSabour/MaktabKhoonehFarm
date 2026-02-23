import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.course import Course
from app.models.enums import LogLevel
from app.services.local_runner import run_in_background
from app.services.task_dispatcher import celery_worker_available
from app.services.task_logger import log_task_sync
from app.tasks.course_tasks import ai_translate_task, process_course_task, process_subtitles_task

router = APIRouter()


@router.post('/courses/{course_id}/process/')
def start_processing_pipeline(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    if celery_worker_available():
        task = process_course_task.delay(str(course_id))
        log_task_sync(
            db,
            level=LogLevel.INFO,
            message='Download pipeline queued',
            task_type='download',
            status='queued',
            course_id=course.id,
            details={'task_id': task.id},
        )
        return {'task_id': task.id, 'status': 'queued', 'mode': 'celery'}

    log_task_sync(
        db,
        level=LogLevel.WARNING,
        message='No Celery worker detected; running download pipeline in local background worker.',
        task_type='download',
        status='queued',
        course_id=course.id,
    )
    run_in_background(lambda: process_course_task.run(str(course_id)), name=f'acms-download-{course.id}')
    return {'status': 'queued', 'mode': 'local_background'}


@router.post('/courses/{course_id}/process-subtitles/')
def start_subtitle_processing(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    if celery_worker_available():
        task = process_subtitles_task.delay(str(course_id))
        log_task_sync(
            db,
            level=LogLevel.INFO,
            message='Subtitle processing queued',
            task_type='process_subtitle',
            status='queued',
            course_id=course.id,
            details={'task_id': task.id},
        )
        return {'task_id': task.id, 'status': 'queued', 'mode': 'celery'}

    log_task_sync(
        db,
        level=LogLevel.WARNING,
        message='No Celery worker detected; running subtitle processing in local background worker.',
        task_type='process_subtitle',
        status='queued',
        course_id=course.id,
    )
    run_in_background(lambda: process_subtitles_task.run(str(course_id)), name=f'acms-subtitle-{course.id}')
    return {'status': 'queued', 'mode': 'local_background'}


@router.post('/courses/{course_id}/ai-translate/')
def start_ai_translation(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    if celery_worker_available():
        task = ai_translate_task.delay(str(course_id))
        log_task_sync(
            db,
            level=LogLevel.INFO,
            message='AI translation queued',
            task_type='ai_translate',
            status='queued',
            course_id=course.id,
            details={'task_id': task.id},
        )
        return {'task_id': task.id, 'status': 'queued', 'mode': 'celery'}

    log_task_sync(
        db,
        level=LogLevel.WARNING,
        message='No Celery worker detected; running AI translation in local background worker.',
        task_type='ai_translate',
        status='queued',
        course_id=course.id,
    )
    run_in_background(lambda: ai_translate_task.run(str(course_id)), name=f'acms-ai-{course.id}')
    return {'status': 'queued', 'mode': 'local_background'}
