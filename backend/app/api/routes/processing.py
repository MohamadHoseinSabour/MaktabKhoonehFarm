import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.course import Course
from app.tasks.course_tasks import ai_translate_task, process_course_task, process_subtitles_task

router = APIRouter()


@router.post('/courses/{course_id}/process/')
def start_processing_pipeline(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    task = process_course_task.delay(str(course_id))
    return {'task_id': task.id, 'status': 'queued'}


@router.post('/courses/{course_id}/process-subtitles/')
def start_subtitle_processing(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    task = process_subtitles_task.delay(str(course_id))
    return {'task_id': task.id, 'status': 'queued'}


@router.post('/courses/{course_id}/ai-translate/')
def start_ai_translation(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    task = ai_translate_task.delay(str(course_id))
    return {'task_id': task.id, 'status': 'queued'}