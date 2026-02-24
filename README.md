# Automated Course Migration System (ACMS)

Phase-1 scaffold for course scraping, link management, download/processing pipeline, AI translation, and dashboard/admin UI.

## Stack
- Backend: FastAPI + SQLAlchemy + Celery + Redis
- Frontend: Next.js (App Router, TypeScript)
- Database: SQLite (default) or PostgreSQL

## Quick Start
1. Create env file:
   - `cp .env.example .env`
2. Backend setup:
   - `cd backend`
   - `python -m venv .venv`
   - `.venv\Scripts\activate` (Windows)
   - `pip install -r requirements.txt`
   - `cd ..`
3. Frontend setup:
   - `cd frontend`
   - `npm install`
   - `cd ..`
4. Run backend:
   - `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload`
5. Run frontend (new terminal):
   - `cd frontend`
   - `npm run dev`
6. Open:
   - Frontend: `http://localhost:3000`
   - Backend docs: `http://localhost:8000/docs`

## Core API
- `POST /api/courses/` add new course + queue scrape
- `POST /api/courses/{id}/links/` parse/match links
- `POST /api/courses/{id}/process/` queue download pipeline
- `POST /api/courses/{id}/process-subtitles/` queue subtitle processor
- `POST /api/courses/{id}/ai-translate/` queue AI translation
- `GET /api/dashboard/stats/` global stats
- `GET /api/courses/{id}/progress/` per-course progress
- `WS /ws/courses/{id}/live-logs/` live logs

## Tests
Run backend tests:
- `cd backend`
- `pytest`

## Notes
- If Redis/Celery worker is not running, task routes automatically fall back to local background execution.
- AI keys are encrypted at rest (`ai_configs.api_key`).
- Debug mode limits download pipeline to first episode.
- Storage path layout is inside project `storage/`, e.g. `storage/courses/{course_slug}/...`.
