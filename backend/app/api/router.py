from fastapi import APIRouter

from app.api.routes import ai_configs, courses, dashboard, episodes, links, logs, processing, settings, upload_automation

api_router = APIRouter()
api_router.include_router(courses.router, prefix='/courses', tags=['courses'])
api_router.include_router(episodes.router, tags=['episodes'])
api_router.include_router(links.router, tags=['links'])
api_router.include_router(processing.router, tags=['processing'])
api_router.include_router(settings.router, prefix='/settings', tags=['settings'])
api_router.include_router(ai_configs.router, prefix='/ai-configs', tags=['ai-configs'])
api_router.include_router(logs.router, tags=['logs'])
api_router.include_router(dashboard.router, tags=['dashboard'])
api_router.include_router(upload_automation.router, tags=['upload-automation'])
