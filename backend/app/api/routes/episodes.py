import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.episode import Episode
from app.models.enums import AssetStatus
from app.schemas.episode import EpisodeOut, EpisodeUpdate

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