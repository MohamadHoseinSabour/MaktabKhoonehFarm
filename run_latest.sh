#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== ACMS Build and Run ==="
echo

# ─── 1. Pull latest code ───
echo "[1/6] Pulling latest code..."
if git rev-parse --is-inside-work-tree &>/dev/null; then
  if git remote get-url origin &>/dev/null; then
    git pull --ff-only || { echo "git pull failed. Resolve issues, then run again."; exit 1; }
  else
    echo "Git remote 'origin' not configured. Skipping pull."
  fi
else
  echo "Not a Git repository. Skipping pull."
fi

# ─── 2. Detect local IP ───
echo "[2/6] Detecting local IP..."
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
LOCAL_IP="${LOCAL_IP:-127.0.0.1}"
echo "    → $LOCAL_IP"

# Set the API base URL so Next.js build and runtime can reach the backend
export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://${LOCAL_IP}:8000}"
echo "    → API_BASE: $NEXT_PUBLIC_API_BASE_URL"

# ─── 3. Backend setup ───
echo "[3/6] Preparing backend environment..."
if [ ! -f "backend/.venv/bin/python" ]; then
  python3 -m venv backend/.venv
fi
backend/.venv/bin/python -m pip install --quiet -r backend/requirements.txt

# ─── 4. Frontend setup ───
echo "[4/6] Installing frontend packages..."
cd frontend
npm install --silent
echo "[5/6] Building frontend..."
npm run build
cd "$ROOT"

# ─── 5. Create storage dirs ───
mkdir -p storage logs

# ─── 6. Start services ───
echo "[6/6] Starting services..."

# Backend
backend/.venv/bin/uvicorn app.main:app \
  --app-dir backend \
  --host 0.0.0.0 \
  --port 8000 &
BACKEND_PID=$!

# Celery Worker
cd backend
../backend/.venv/bin/celery -A app.core.celery_app worker --loglevel=info &
CELERY_PID=$!
cd "$ROOT"

# Frontend
cd frontend
npm run start -- -H 0.0.0.0 -p 3000 &
FRONTEND_PID=$!
cd "$ROOT"

echo
echo "Frontend:     http://${LOCAL_IP}:3000"
echo "Backend docs: http://${LOCAL_IP}:8000/docs"
echo
echo "Backend PID:  $BACKEND_PID"
echo "Celery PID:   $CELERY_PID"
echo "Frontend PID: $FRONTEND_PID"
echo
echo "Press Ctrl+C to stop all services."

# Trap Ctrl+C to kill all
trap "kill $BACKEND_PID $CELERY_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
