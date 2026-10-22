@echo off
chcp 65001 >nul
title PBL4 - Face AI Dashboard Launcher
cd /d "%~dp0pbl4-face-ai"

echo ========================================================
echo   🤖 KHỞI ĐỘNG HỆ THỐNG FACE AI - PBL4
echo ========================================================
echo.

REM Kích hoạt môi trường ảo Python 3.11 và chạy GUI Dashboard
".\.venv\Scripts\python.exe" "gui.py"

pause
