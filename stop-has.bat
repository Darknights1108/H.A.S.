@echo off
title HAS - stop
cd /d "%~dp0"
echo Stopping HAS containers...
docker compose stop
echo.
echo Done. All data is preserved. Run start-has.bat to start again.
pause
