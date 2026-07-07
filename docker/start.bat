@echo off
setlocal enabledelayedexpansion

echo ======================================
echo AI Agent Platform - Docker Startup
echo ======================================

REM 1. Stop and remove all containers completely
echo [1/3] Removing old containers...
docker compose down --remove-orphans
docker rm -f ai-agent-api ai-agent-worker ai-agent-web 2>nul || true
docker rm -f ai-agent-mysql ai-agent-minio 2>nul || true

REM 2. Start services using EXISTING images.
REM    No --build by default: api and worker bind-mount host source into /app
REM    and run uvicorn with --reload, so code changes apply on restart without
REM    rebuilding the image. Only rebuild when requirements.txt or the
REM    Dockerfile changes, by running: docker compose build api worker
REM    If the api or worker images are missing, build them once.
docker image inspect ai-agent-api:latest >nul 2>&1
if not errorlevel 1 goto start
echo [2/3] api/worker images missing - building once
docker compose build api worker
:start
echo [2/3] Starting services from existing images...
docker compose up -d

echo [3/3] Waiting for services to be healthy...
timeout /t 10 /nobreak >nul
docker compose ps

echo.
echo ======================================
echo All services are running!
echo ======================================
echo API:      http://localhost:8010
echo Web:      http://localhost:80
echo MinIO:    http://localhost:9001
echo MySQL:    localhost:3306
echo.
echo Default admin account:
echo   Username: admin
echo   Password: admin123
echo ======================================
