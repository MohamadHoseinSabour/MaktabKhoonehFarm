import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.course import Course
from app.models.episode import Episode
from app.models.enums import AssetStatus, QueueStatus
from app.models.processing_queue import ProcessingQueue
from app.models.task_log import TaskLog
from app.schemas.dashboard import CourseProgressOut, DashboardStatsOut
from app.services.course_service import calculate_course_progress

router = APIRouter()


@router.get('/dashboard/stats/', response_model=DashboardStatsOut)
def dashboard_stats(db: Session = Depends(get_db)):
    total_courses = db.query(func.count(Course.id)).scalar() or 0
    active_downloads = (
        db.query(func.count(Episode.id)).filter(Episode.video_status == AssetStatus.DOWNLOADING).scalar() or 0
    )
    queued_tasks = (
        db.query(func.count(ProcessingQueue.id)).filter(ProcessingQueue.status == QueueStatus.QUEUED).scalar() or 0
    )

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    failed_tasks_24h = (
        db.query(func.count(TaskLog.id))
        .filter(TaskLog.status == 'failed', TaskLog.created_at >= since)
        .scalar()
        or 0
    )

    return DashboardStatsOut(
        total_courses=total_courses,
        active_downloads=active_downloads,
        queued_tasks=queued_tasks,
        failed_tasks_24h=failed_tasks_24h,
    )


@router.get('/courses/{course_id}/progress/', response_model=CourseProgressOut)
def course_progress(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    episodes = db.query(Episode).filter(Episode.course_id == course.id).all()
    return CourseProgressOut(**calculate_course_progress(course, episodes))
