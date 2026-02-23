import uuid

from sqlalchemy.orm import Session

from app.models.enums import LogLevel
from app.models.task_log import TaskLog
from app.ws.manager import live_log_manager


def _persist_log(
    db: Session,
    level: LogLevel,
    message: str,
    task_type: str,
    status: str,
    course_id: uuid.UUID | None = None,
    episode_id: uuid.UUID | None = None,
    details: dict | None = None,
) -> TaskLog:
    entry = TaskLog(
        course_id=course_id,
        episode_id=episode_id,
        level=level,
        message=message,
        task_type=task_type,
        status=status,
        details=details or {},
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def log_task_sync(
    db: Session,
    level: LogLevel,
    message: str,
    task_type: str,
    status: str,
    course_id: uuid.UUID | None = None,
    episode_id: uuid.UUID | None = None,
    details: dict | None = None,
) -> TaskLog:
    return _persist_log(
        db=db,
        level=level,
        message=message,
        task_type=task_type,
        status=status,
        course_id=course_id,
        episode_id=episode_id,
        details=details,
    )


async def log_task(
    db: Session,
    level: LogLevel,
    message: str,
    task_type: str,
    status: str,
    course_id: uuid.UUID | None = None,
    episode_id: uuid.UUID | None = None,
    details: dict | None = None,
) -> TaskLog:
    entry = _persist_log(
        db=db,
        level=level,
        message=message,
        task_type=task_type,
        status=status,
        course_id=course_id,
        episode_id=episode_id,
        details=details,
    )

    if course_id:
        await live_log_manager.broadcast(
            str(course_id),
            {
                'id': str(entry.id),
                'level': entry.level.value,
                'message': entry.message,
                'task_type': entry.task_type,
                'status': entry.status,
                'details': entry.details,
                'created_at': entry.created_at.isoformat(),
            },
        )

    return entry
