# @echo off
# python -m venv venv
# call venv\Scripts\activate
# pip install -r requirements.txt
# python app.py
# pause


@echo off
title CPU Performance Optimization Simulator

cd /d "%~dp0"

set "PYTHON=C:\Users\Tamil maran\AppData\Local\Programs\Python\Python313\python.exe"

echo =====================================
echo   CPU PERFORMANCE OPTIMIZATION
echo =====================================

echo.
echo [1/4] Checking Python...
"%PYTHON%" --version

if errorlevel 1 (
    echo Python not found!
    pause
    exit /b 1
)

echo.
echo [2/4] Creating virtual environment...

if not exist "venv\Scripts\python.exe" (
    "%PYTHON%" -m venv venv
)

if errorlevel 1 (
    echo Virtual environment creation failed!
    pause
    exit /b 1
)

echo.
echo [3/4] Installing requirements...

"venv\Scripts\python.exe" -m pip install -r requirements.txt

if errorlevel 1 (
    echo Package installation failed!
    pause
    exit /b 1
)

echo.
echo [4/4] Starting Flask application...

"venv\Scripts\python.exe" app.py

pause

