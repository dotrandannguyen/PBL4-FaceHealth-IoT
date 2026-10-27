@echo off
title PBL4 - Face AI Dashboard Launcher
cd /d "%~dp0pbl4-face-ai"

echo ========================================================
echo   PBL4 - FACE AI DASHBOARD LAUNCHER
echo ========================================================
echo.

REM Kich hoat moi truong ao Python 3.11 va chay GUI Dashboard
if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" "gui.py"
) else (
    python "gui.py"
)

if errorlevel 1 (
    echo.
    echo [ERROR] Ung dung ket thuc voi ma loi %errorlevel%.
    pause
)
