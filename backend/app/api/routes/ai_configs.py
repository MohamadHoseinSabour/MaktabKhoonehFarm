import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.ai_config import AIConfig
from app.schemas.ai_config import AIConfigCreate, AIConfigOut, AIConfigTestResponse, AIConfigUpdate
from app.services.ai.openai_provider import OpenAIProvider
from app.services.ai.security import decrypt_secret, encrypt_secret

router = APIRouter()
GAPGPT_BASE_URL = 'https://api.gapgpt.app/v1'


@router.get('/', response_model=list[AIConfigOut])
def list_ai_configs(db: Session = Depends(get_db)):
    return db.query(AIConfig).order_by(AIConfig.priority.asc()).all()


@router.post('/', response_model=AIConfigOut)
def create_ai_config(payload: AIConfigCreate, db: Session = Depends(get_db)):
    if payload.is_active:
        db.query(AIConfig).update({AIConfig.is_active: False})

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
    if data.get('is_active') is True:
        db.query(AIConfig).filter(AIConfig.id != config.id).update({AIConfig.is_active: False})

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
        api_key = decrypt_secret(config.api_key)
        if not config.model_name:
            raise ValueError('Model name is missing')

        provider_name = config.provider.lower()
        if provider_name in {'openai', 'gapgpt'}:
            endpoint_url = config.endpoint_url or (GAPGPT_BASE_URL if provider_name == 'gapgpt' else None)
            provider = OpenAIProvider(api_key=api_key, model=config.model_name, endpoint_url=endpoint_url)
            result = provider.translate('Reply only with: OK')
            if not result:
                raise ValueError('Model returned an empty response')
            return AIConfigTestResponse(success=True, message='Connection successful')

        return AIConfigTestResponse(success=False, message=f'Provider {config.provider} is not supported for live test yet')
    except Exception as exc:
        return AIConfigTestResponse(success=False, message=f'Configuration test failed: {exc}')


@router.post('/{config_id}/activate/', response_model=AIConfigOut)
def activate_ai_config(config_id: uuid.UUID, db: Session = Depends(get_db)):
    config = db.query(AIConfig).filter(AIConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail='AI config not found')

    db.query(AIConfig).update({AIConfig.is_active: False})
    config.is_active = True
    db.commit()
    db.refresh(config)
    return config


@router.post('/{config_id}/deactivate/', response_model=AIConfigOut)
def deactivate_ai_config(config_id: uuid.UUID, db: Session = Depends(get_db)):
    config = db.query(AIConfig).filter(AIConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail='AI config not found')

    config.is_active = False
    db.commit()
    db.refresh(config)
    return config


@router.delete('/{config_id}/')
def delete_ai_config(config_id: uuid.UUID, db: Session = Depends(get_db)):
    config = db.query(AIConfig).filter(AIConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail='AI config not found')

    db.delete(config)
    db.commit()
    return {'deleted': True}
