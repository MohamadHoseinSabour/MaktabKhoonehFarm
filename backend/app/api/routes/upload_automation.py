from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.upload import FirefoxUploadNavigator, UploadAuthExpiredError, UploadConfigurationError

router = APIRouter()


@router.post('/upload-automation/validate-cookies/')
def validate_upload_cookies(db: Session = Depends(get_db)):
    try:
        navigator = FirefoxUploadNavigator(db)
        return navigator.validate_cookies()
    except UploadAuthExpiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UploadConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
