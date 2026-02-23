from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.setting import Setting
from app.schemas.setting import SettingIn, SettingOut

router = APIRouter()


@router.get('/', response_model=list[SettingOut])
def list_settings(db: Session = Depends(get_db)):
    return db.query(Setting).order_by(Setting.category.asc().nullslast(), Setting.key.asc()).all()


@router.put('/', response_model=list[SettingOut])
def upsert_settings(payload: list[SettingIn], db: Session = Depends(get_db)):
    for item in payload:
        setting = db.query(Setting).filter(Setting.key == item.key).first()
        if not setting:
            setting = Setting(key=item.key, value=item.value, category=item.category, description=item.description)
            db.add(setting)
        else:
            setting.value = item.value
            setting.category = item.category
            setting.description = item.description

    db.commit()
    return db.query(Setting).order_by(Setting.category.asc().nullslast(), Setting.key.asc()).all()