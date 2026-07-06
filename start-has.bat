@echo off
setlocal
title HAS - Hiring Automation System
cd /d "%~dp0"

echo ============================================
echo   HAS - Hiring Automation System launcher
echo ============================================
echo.

echo [1/4] Checking Docker...
docker info >nul 2>&1
if %errorlevel%==0 goto docker_ready

echo       Docker engine not running - starting Docker Desktop...
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
) else (
    echo       ERROR: Docker Desktop not found at "%ProgramFiles%\Docker\Docker".
    echo       Please install Docker Desktop or start it manually, then re-run.
    pause
    exit /b 1
)

set /a tries=0
:wait_docker
ping -n 4 127.0.0.1 >nul
docker info >nul 2>&1
if %errorlevel%==0 goto docker_ready
set /a tries+=1
if %tries% geq 60 (
    echo       ERROR: Docker did not become ready within 3 minutes.
    pause
    exit /b 1
)
echo       waiting for Docker engine ... %tries%
goto wait_docker

:docker_ready
echo       Docker is running.
echo.

echo [2/4] Starting HAS containers...
REM  usage: start-has.bat build   ^<- rebuilds images (after code changes)
if /i "%~1"=="build" (
    docker compose up -d --build
) else (
    docker compose up -d
)
if not %errorlevel%==0 (
    echo       ERROR: docker compose failed. See output above.
    pause
    exit /b 1
)
echo.

echo [3/4] Waiting for backend API...
set /a tries=0
:wait_backend
curl -s -o nul -m 3 http://localhost:8000/api/health >nul 2>&1
if %errorlevel%==0 goto backend_ready
set /a tries+=1
if %tries% geq 60 (
    echo       ERROR: backend not responding. Check logs: docker compose logs backend
    pause
    exit /b 1
)
ping -n 3 127.0.0.1 >nul
goto wait_backend

:backend_ready
echo       Backend is up.
set /a tries=0
:wait_frontend
curl -s -o nul -m 5 http://localhost:3000 >nul 2>&1
if %errorlevel%==0 goto frontend_ready
set /a tries+=1
if %tries% geq 45 goto frontend_ready
ping -n 3 127.0.0.1 >nul
goto wait_frontend

:frontend_ready
echo       Frontend is up.
echo.

echo [4/4] Opening browser...
start "" http://localhost:3000

echo.
echo   HAS is running:
echo     App        http://localhost:3000
echo     API docs   http://localhost:8000/docs
echo     MinIO      http://localhost:9001
echo.
echo   Stop with stop-has.bat  (data is kept)
echo   Rebuild after code changes:  start-has.bat build
echo.
ping -n 9 127.0.0.1 >nul
endlocal
