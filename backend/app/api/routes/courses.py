import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.course import Course
from app.models.episode import Episode
from app.models.enums import AssetStatus, CourseStatus
from app.schemas.course import CourseCreate, CourseDetailOut, CourseOut, CourseUpdate, ToggleDebugResponse
from app.services.course_service import course_storage_root
from app.tasks.course_tasks import scrape_course_task

router = APIRouter()


@router.post('/', response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, db: Session = Depends(get_db)):
    existing = db.query(Course).filter(Course.source_url == str(payload.source_url)).first()
    if existing:
        return existing

    course = Course(source_url=str(payload.source_url), debug_mode=payload.debug_mode, status=CourseStatus.SCRAPING)
    db.add(course)
    db.commit()
    db.refresh(course)

    scrape_course_task.delay(str(course.id))
    return course


@router.get('/', response_model=list[CourseOut])
def list_courses(db: Session = Depends(get_db)):
    return db.query(Course).order_by(Course.created_at.desc()).all()


@router.get('/{course_id}/', response_model=CourseDetailOut)
def get_course(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    episodes = (
        db.query(Episode)
        .filter(Episode.course_id == course.id)
        .order_by(Episode.sort_order.asc(), Episode.episode_number.asc().nullslast())
        .all()
    )
    course.episodes = episodes
    return course


@router.put('/{course_id}/', response_model=CourseOut)
def update_course(course_id: uuid.UUID, payload: CourseUpdate, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(course, key, value)

    db.commit()
    db.refresh(course)
    return course


@router.delete('/{course_id}/', status_code=status.HTTP_204_NO_CONTENT)
def delete_course(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    try:
        root = course_storage_root(course)
        if root.exists():
            shutil.rmtree(root)
    except Exception:
        pass

    db.delete(course)
    db.commit()
    return None


@router.post('/{course_id}/scrape/', response_model=CourseOut)
def scrape_course(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    scrape_course_task.delay(str(course.id))
    db.refresh(course)
    return course


@router.post('/{course_id}/toggle-debug/', response_model=ToggleDebugResponse)
def toggle_debug(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    course.debug_mode = not course.debug_mode
    db.commit()

    return ToggleDebugResponse(course_id=course.id, debug_mode=course.debug_mode)


@router.post('/{course_id}/retry-all-failed/')
def retry_all_failed(course_id: uuid.UUID, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail='Course not found')

    episodes = db.query(Episode).filter(Episode.course_id == course_id).all()
    retried = 0

    for episode in episodes:
        if episode.video_status == AssetStatus.ERROR:
            episode.video_status = AssetStatus.PENDING
            retried += 1
        if episode.subtitle_status == AssetStatus.ERROR:
            episode.subtitle_status = AssetStatus.PENDING
            retried += 1
        if episode.exercise_status == AssetStatus.ERROR:
            episode.exercise_status = AssetStatus.PENDING
            retried += 1

    db.commit()
    return {'retried': retried}
