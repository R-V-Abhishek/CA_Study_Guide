@echo off
title CA Final Study Companion - Setup
cd /d "%~dp0"

echo ========================================================
echo   CA Final Study Companion - Windows Setup
echo ========================================================

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found in PATH!
    echo Please install Python 3.12+ from https://www.python.org/downloads/
    echo Make sure to check "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

python setup.py
pause
