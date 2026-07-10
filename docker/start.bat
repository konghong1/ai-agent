@echo off
setlocal

echo ======================================
echo AI Agent Platform - Docker Startup
echo ======================================

REM Ensure Docker credential helper (docker-credential-desktop) is on PATH,
REM otherwise "docker compose build" fails with "executable file not found".
set "DOCKER_BIN=C:\Program Files\Docker\Docker\resources\bin"
if exist "%DOCKER_BIN%" set "PATH=%DOCKER_BIN%;%PATH%"

set "BAT_DIR=%~dp0"
set "BAT_DIR=%BAT_DIR:~0,-1%"
for %%I in ("%BAT_DIR%") do set "PROJECT_ROOT=%%~dpI"
set "WEB_DIR=%PROJECT_ROOT%web"

echo [1/5] Building frontend
if not exist "%WEB_DIR%\node_modules" (
  echo   Installing web dependencies
  cd /d "%WEB_DIR%"
  call npm install --no-audit --no-fund
)
cd /d "%WEB_DIR%"
call npm run build
if errorlevel 1 (
  echo   WARN Frontend build failed, keeping previous dist
) else (
  echo   Frontend build OK
)
cd /d "%BAT_DIR%"

echo [2/5] Checking Docker daemon
set "DAEMON_OK=0"
set "TRY=0"
:daemon_retry
set /a TRY=TRY+1
docker info >nul 2>&1
if not errorlevel 1 (
  set "DAEMON_OK=1"
  goto daemon_done
)
if %TRY% GEQ 6 goto daemon_fail
echo   daemon busy/not ready, retrying %TRY%/6
timeout /t 3 /nobreak >nul
goto daemon_retry
:daemon_done
echo   Docker daemon is up
goto daemon_cont
:daemon_fail
echo   ERROR: Docker daemon is not reachable.
echo   Please start Docker Desktop first, then re-run this script.
echo   (e.g. start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe")
exit /b 1
:daemon_cont

echo [3/5] Removing old containers
docker compose down --remove-orphans
docker rm -f ai-agent-api ai-agent-worker ai-agent-web 2>nul
docker rm -f ai-agent-mysql ai-agent-minio 2>nul

docker image inspect ai-agent-api:latest >nul 2>&1
if not errorlevel 1 goto start
echo [4/5] api worker images missing, building once
docker compose build api worker
:start
echo [5/5] Starting services
docker compose up -d
if errorlevel 1 (
  echo   ERROR: failed to bring up services
  exit /b 1
)

echo Waiting for services to be healthy
timeout /t 10 /nobreak >nul
docker compose ps

echo.
echo ======================================
echo All services are running
echo ======================================
echo API:      http://localhost:8010
echo Web:      http://localhost:80
echo MinIO:    http://localhost:9001
echo MySQL:    localhost:3306
echo.
echo Default admin account
echo   Username: admin
echo   Password: admin123
echo ======================================

endlocal
