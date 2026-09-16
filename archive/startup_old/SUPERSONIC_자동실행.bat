@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "API_FILE=supersonic_api_enterprise_v3_2_계정상태관리.py"
set "COLLECTOR_FILE=supersonic_collector_core_v2_3_자동시작.py"
set "LOG_DIR=%~dp0logs"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

where py >nul 2>&1
if %errorlevel%==0 (
    set "PY=py"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PY=python"
    ) else (
        echo [오류] Python을 찾을 수 없습니다.
        pause
        exit /b 1
    )
)

if not exist "%API_FILE%" (
    echo [오류] %API_FILE% 파일이 없습니다.
    pause
    exit /b 1
)
if not exist "%COLLECTOR_FILE%" (
    echo [오류] %COLLECTOR_FILE% 파일이 없습니다.
    pause
    exit /b 1
)

echo SUPERSONIC 자동실행 시작...

rem API는 별도 최소화 창으로 실행
start "SUPERSONIC API" /min cmd /c ""%PY%" "%~dp0%API_FILE%" >> "%LOG_DIR%\api.log" 2>&1"

rem Collector는 Chrome 상태 확인이 필요하므로 일반 창으로 실행
timeout /t 3 /nobreak >nul
start "SUPERSONIC Collector" cmd /c ""%PY%" "%~dp0%COLLECTOR_FILE%" >> "%LOG_DIR%\collector.log" 2>&1"

echo API / Collector 실행 명령 완료.
exit /b 0
