@echo off
REM ======================================================
REM   MediAd View - Windows Print Agent Launcher
REM   Place SumatraPDF.exe in the same folder for best results
REM ======================================================
cd /d "%~dp0"
title MediAd View Print Agent

REM Find Python (prefer "py" launcher, fallback to "python")
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py print_agent.py
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        python print_agent.py
    ) else (
        echo.
        echo ERROR: Python is not installed or not on PATH.
        echo Please install Python 3.10+ from https://www.python.org/downloads/
        echo and re-run this script.
        echo.
        pause
        exit /b 1
    )
)

pause
