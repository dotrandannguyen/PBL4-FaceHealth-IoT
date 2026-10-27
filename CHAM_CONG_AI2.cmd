@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_services.ps1" -AIOnly
if errorlevel 1 (
  pause
  exit /b 1
)
cd /d "%~dp0pbl4-face-ai"
".venv-pbl4\Scripts\python.exe" -u -B gui_attendance.py
if errorlevel 1 pause
