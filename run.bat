@echo off
chcp 65001 >nul
title MoBi - Phone Shop POS and Maintenance Hub
echo ========================================================
echo   Starting MoBi Desktop System (Offline 100%%)...
echo ========================================================

if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe run.py %*
) else (
    python run.py %*
)

if %errorlevel% neq 0 (
    echo.
    echo [!] Application stopped with an exit code.
    pause
)
