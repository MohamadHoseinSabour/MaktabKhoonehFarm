import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.ai_config import AIConfig
from app.schemas.ai_config import AIConfigCreate, AIConfigOut, AIConfigTestResponse, AIConfigUpdate
from app.services.ai.security import decrypt_secret, encrypt_secret

router = APIRouter()


@router.get('/', response_model=list[AIConfigOut])
def list_ai_configs(db: Session = Depends(get_db)):
    return db.query(AIConfig).order_by(AIConfig.priority.asc()).all()


@router.post('/', response_model=AIConfigOut)
def create_ai_config(payload: AIConfigCreate, db: Session = Depends(get_db)):
    config = AIConfig(
        provider=payload.provider,
        api_key=encrypt_secret(payload.api_key),
        model_name=payload.model_name,
        endpoint_url=payload.endpoint_url,
        is_active=payload.is_active,
        priority=payload.priority,
        rate_limit=payload.rate_limit,
        monthly_budget=payload.monthly_budget,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.put('/{config_id}/', response_model=AIConfigOut)
def update_ai_config(config_id: uuid.UUID, payload: AIConfigUpdate, db: Session = Depends(get_db)):
    config = db.query(AIConfig).filter(AIConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail='AI config not found')

    data = payload.model_dump(exclude_unset=True)
    if 'api_key' in data and data['api_key'] is not None:
        data['api_key'] = encrypt_secret(data['api_key'])

    for key, value in data.items():
        setattr(config, key, value)

    db.commit()
    db.refresh(config)
    return config


@router.post('/{config_id}/test/', response_model=AIConfigTestResponse)
def test_ai_config(config_id: uuid.UUID, db: Session = Depends(get_db)):
    config = db.query(AIConfig).filter(AIConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail='AI config not found')

    try:
        _ = decrypt_secret(config.api_key)
        if not config.model_name:
            raise ValueError('Model name is missing')
        return AIConfigTestResponse(success=True, message='Configuration is valid')
    except Exception as exc:
        return AIConfigTestResponse(success=False, message=f'Configuration test failed: {exc}')