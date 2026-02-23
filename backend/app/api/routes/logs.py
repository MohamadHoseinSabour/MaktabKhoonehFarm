import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.task_log import TaskLog
from app.schemas.log import TaskLogOut

router = APIRouter()


@router.get('/logs/', response_model=list[TaskLogOut])
def list_logs(
    db: Session = Depends(get_db),
    level: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    query = db.query(TaskLog)

    if level:
        query = query.filter(TaskLog.level == level)
    if task_type:
        query = query.filter(TaskLog.task_type == task_type)

    return query.order_by(TaskLog.created_at.desc()).limit(limit).all()


@router.get('/courses/{course_id}/logs/', response_model=list[TaskLogOut])
def list_course_logs(
    course_id: uuid.UUID,
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=1000),
):
    return (
        db.query(TaskLog)
        .filter(TaskLog.course_id == course_id)
        .order_by(TaskLog.created_at.desc())
        .limit(limit)
        .all()
    )
