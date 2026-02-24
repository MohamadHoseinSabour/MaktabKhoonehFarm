@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo === ACMS Build and Run ===
echo.

echo [1/6] Pulling latest code...
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo Not a Git repository. Skipping pull.
) else (
  git remote get-url origin >nul 2>&1
  if errorlevel 1 (
    echo Git remote "origin" not configured. Skipping pull.
  ) else (
    git pull --ff-only
    if errorlevel 1 (
      echo git pull failed. Resolve issues, then run again.
      goto :error
    )
  )
)

echo [2/6] Detecting local IP...
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$ip=(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.AddressState -eq 'Preferred' } | Select-Object -First 1 -ExpandProperty IPAddress); if(-not $ip){$ip='127.0.0.1'}; Write-Output $ip"`) do set "LOCAL_IP=%%I"
if not defined LOCAL_IP set "LOCAL_IP=127.0.0.1"

echo [3/6] Preparing backend environment...
if not exist "backend\.venv\Scripts\python.exe" (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv "backend\.venv"
  ) else (
    python -m venv "backend\.venv"
  )
  if errorlevel 1 (
    echo Could not create Python virtual environment.
    goto :error
  )
)
call "backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 goto :error

echo [4/6] Installing frontend packages...
pushd "frontend"
call npm install
if errorlevel 1 (
  popd
  goto :error
)

echo [5/6] Building frontend...
call npm run build
if errorlevel 1 (
  popd
  goto :error
)
popd

echo [6/6] Starting services...
start "ACMS Backend" cmd /k "cd /d ""%ROOT%"" && call ""backend\.venv\Scripts\activate.bat"" && uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000"
start "ACMS Frontend" cmd /k "cd /d ""%ROOT%frontend"" && npm run start -- -H 0.0.0.0 -p 3000"

echo.
echo Frontend: http://%LOCAL_IP%:3000
echo Backend docs: http://%LOCAL_IP%:8000/docs
echo.
echo Wait for both windows to finish startup.
goto :eof

:error
echo.
echo Script stopped because of an error.
exit /b 1
