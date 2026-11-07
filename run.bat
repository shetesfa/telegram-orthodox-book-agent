@echo off
title Telegram Book Search Agent
echo ========================================================
echo   Telegram Book Search Agent
echo ========================================================
echo.

REM 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please install Python from python.org and add it to PATH.
    pause
    exit /b 1
)

REM 2. Activate virtual environment if present
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM 3. Create .env if missing
if not exist ".env" (
    copy .env.example .env >nul
)

REM 4. Ensure directories exist
if not exist "data\downloads" mkdir data\downloads
if not exist "data\database" mkdir data\database
if not exist "logs" mkdir logs

echo Starting backend server on http://127.0.0.1:8080 (Local Network: 0.0.0.0) ...
echo Opening web interface in your default browser...

REM Start browser after 2 seconds in background
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8080"

REM Run FastAPI server with Uvicorn
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
pause
