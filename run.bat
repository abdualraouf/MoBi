@echo off
title MoBi - تشغيل نظام محل الهواتف والصيانة
echo ===================================================
echo جاري تشغيل نظام MoBi لمحل الهواتف والصيانة...
echo ===================================================

if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe run.py
) else (
    python run.py
)

pause
