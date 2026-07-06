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

REM 2. Rebuild and start all services
echo [2/3] Building and starting all services...
docker compose up -d --build

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
