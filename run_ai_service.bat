@echo off
title PBL4 - Face AI Service (Port 5001)
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   PBL4 - FACE AI REST SERVICE (InsightFace + Camera)
echo ========================================================
echo.

set "TASK_PYTHON=pbl4-face-ai\.venv\Scripts\python.exe"
if not exist "%TASK_PYTHON%" (
    set "TASK_PYTHON=pbl4-face-ai\.venv-pbl4\Scripts\python.exe"
)
if not exist "%TASK_PYTHON%" (
    set "TASK_PYTHON=python"
)

echo [INFO] Dang khoi dong AI Service tren http://127.0.0.1:5001...
echo [INFO] Sau khi san sang, mo trinh duyet truy cap:
echo        http://localhost:8080/?action=face_registration
echo.
echo Nhan Ctrl+C de dung dich vu.
echo ========================================================
echo.

"%TASK_PYTHON%" -B pbl4-face-ai\ai_web_service.py

if errorlevel 1 (
    echo.
    echo [ERROR] AI Service ket thuc voi ma loi %errorlevel%.
    pause
)
