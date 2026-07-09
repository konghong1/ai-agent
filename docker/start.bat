@echo off

echo ======================================
echo AI Agent Platform - Docker Startup
echo ======================================

set "BAT_DIR=%~dp0"
set "BAT_DIR=%BAT_DIR:~0,-1%"
for %%I in ("%BAT_DIR%") do set "PROJECT_ROOT=%%~dpI"
set "WEB_DIR=%PROJECT_ROOT%web"

echo [1/4] Building frontend
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

echo [2/4] Removing old containers
docker compose down --remove-orphans
docker rm -f ai-agent-api ai-agent-worker ai-agent-web 2>nul
docker rm -f ai-agent-mysql ai-agent-minio 2>nul

docker image inspect ai-agent-api:latest >nul 2>&1
if not errorlevel 1 goto start
echo [3/4] api worker images missing, building once
docker compose build api worker
:start
echo [4/4] Starting services
docker compose up -d

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
