from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.init_db import init_db
from app.ws.manager import live_log_manager

configure_logging()

app = FastAPI(title=settings.app_name, version='0.1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.on_event('startup')
def startup() -> None:
    init_db()
    storage = Path(settings.storage_path)
    storage.mkdir(parents=True, exist_ok=True)


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@app.websocket('/ws/courses/{course_id}/live-logs/')
async def ws_live_logs(websocket: WebSocket, course_id: str):
    await live_log_manager.connect(course_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        live_log_manager.disconnect(course_id, websocket)