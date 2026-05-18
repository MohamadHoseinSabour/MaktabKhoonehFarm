@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo === ACMS Build and Run ===
echo.

echo [1/6] Pulling latest code...
@REM git rev-parse --is-inside-work-tree >nul 2>&1
@REM if errorlevel 1 (
@REM   echo Not a Git repository. Skipping pull.
@REM ) else (
@REM   git remote get-url origin >nul 2>&1
@REM   if errorlevel 1 (
@REM     echo Git remote "origin" not configured. Skipping pull.
@REM   ) else (
@REM     git pull --ff-only
@REM     if errorlevel 1 (
@REM       echo git pull failed. Resolve issues, then run again.
@REM       goto :error
@REM     )
@REM   )
@REM ) 

echo [2/6] Detecting local IP...
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$ip=(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.AddressState -eq 'Preferred' } | Select-Object -First 1 -ExpandProperty IPAddress); if(-not $ip){$ip='127.0.0.1'}; Write-Output $ip"`) do set "LOCAL_IP=%%I"
if not defined LOCAL_IP set "LOCAL_IP=127.0.0.1"
set "NEXT_PUBLIC_API_BASE_URL=http://%LOCAL_IP%:8000"
echo     API_BASE: %NEXT_PUBLIC_API_BASE_URL%

echo [3/6] Preparing backend environment...
if not exist "backend\.venv\Scripts\python.exe" (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3.12 -m venv "backend\.venv"
  ) else (
    python -m venv "backend\.venv"
  )
  if errorlevel 1 (
    echo Could not create Python virtual environment.
    goto :error
  )
)
"backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 goto :error

echo [4/6] Installing frontend packages...
pushd "frontend"
if exist "package-lock.json" (
  call npm ci
) else (
  call npm install
)
if errorlevel 1 (
  popd
  goto :error
)

echo [5/6] Building frontend...
set "NODE_OPTIONS=--max-old-space-size=512"
call npm run build
if errorlevel 1 (
  popd
  goto :error
)
popd

echo [6/6] Starting services...
if not exist "storage" mkdir "storage"
if not exist "logs" mkdir "logs"
set "REDIS_AVAILABLE=0"
for /f "usebackq delims=" %%R in (`powershell -NoProfile -Command "if (Test-NetConnection -ComputerName 'localhost' -Port 6379 -InformationLevel Quiet) { '1' } else { '0' }"`) do set "REDIS_AVAILABLE=%%R"

start "ACMS Backend" cmd /k "cd /d ""%ROOT%backend"" && set DEBUG=false && set STORAGE_PATH=%ROOT%storage && set DATABASE_URL=sqlite:///%ROOT:\=/%storage/acms.db && ..\backend\.venv\Scripts\uvicorn.exe app.main:app --app-dir . --host 0.0.0.0 --port 8000"
if "%REDIS_AVAILABLE%"=="1" (
  start "ACMS Celery (optional)" cmd /k "cd /d ""%ROOT%backend"" && set STORAGE_PATH=%ROOT%storage && set DATABASE_URL=sqlite:///%ROOT:\=/%storage/acms.db && ..\backend\.venv\Scripts\celery.exe -A app.tasks.celery_app worker --pool=solo --loglevel=info"
) else (
  echo Redis is not reachable on localhost:6379. Skipping Celery worker.
  echo Background tasks will run in local fallback mode.
)
start "ACMS Frontend" cmd /k "cd /d ""%ROOT%frontend"" && set NEXT_PUBLIC_API_BASE_URL=%NEXT_PUBLIC_API_BASE_URL% && npm run start -- -H 0.0.0.0 -p 3000"

echo.
echo Frontend: http://%LOCAL_IP%:3000
echo Backend docs: http://%LOCAL_IP%:8000/docs
echo API Base: %NEXT_PUBLIC_API_BASE_URL%
echo.
echo Wait for both windows to finish startup.
goto :eof

:error
echo.
echo Script stopped because of an error.
exit /b 1
