@echo off
cd /d "%~dp0"

rem HTTPS production mode: force Secure session cookies
set "SUPERSONIC_PRODUCTION=1"

where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py"
) else (
  where python >nul 2>&1
  if %errorlevel%==0 (
    set "PY=python"
  ) else (
    echo Python not found.
    pause
    exit /b 1
  )
)

if not exist "supersonic_api_run.py" (
  echo supersonic_api_run.py not found.
  pause
  exit /b 1
)

if not exist "supersonic_collector_run.py" (
  echo supersonic_collector_run.py not found.
  pause
  exit /b 1
)

start "SUPERSONIC API" /min cmd /k %PY% "%~dp0supersonic_api_run.py"
timeout /t 3 /nobreak >nul
start "SUPERSONIC Collector" cmd /k %PY% "%~dp0supersonic_collector_run.py"

exit /b 0
