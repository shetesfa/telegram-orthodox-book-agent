@echo off
title Telegram Book Search Agent - Setup
echo ========================================================
echo   Telegram Book Search Agent - Setup & Installation
echo ========================================================
echo.

REM 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please install Python 3.10+ from python.org and check "Add to PATH".
    pause
    exit /b 1
)

echo [1/4] Python found.
echo.

REM 2. Create Virtual Environment if not exists
if not exist "venv" (
    echo [2/4] Creating Python virtual environment (venv)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [WARNING] Could not create venv. Proceeding with global/user Python.
    ) else (
        echo Virtual environment created successfully.
    )
) else (
    echo [2/4] Virtual environment already exists.
)
echo.

REM 3. Activate and Install dependencies
echo [3/4] Installing / Upgrading required packages...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    python -m pip install --upgrade pip
    pip install -r requirements.txt
)

if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies. Check your internet connection.
    pause
    exit /b 1
)
echo Dependencies installed successfully.
echo.

REM 4. Copy .env.example if .env does not exist
if not exist ".env" (
    echo [4/4] Creating .env from .env.example...
    copy .env.example .env >nul
    echo .env created. You can optionally add your TELEGRAM_API_ID and TELEGRAM_API_HASH in .env
    echo or connect directly from the Web UI!
) else (
    echo [4/4] Existing .env file found.
)
echo.

echo ========================================================
echo   Setup Completed Successfully!
echo   Run 'run.bat' to start the application.
echo ========================================================
pause
