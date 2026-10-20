@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_services.ps1"
if errorlevel 1 (
  pause
  exit /b 1
)
start "" "http://localhost:8080"
