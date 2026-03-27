@echo off
echo ================================
echo  Jedi Desktop Controller Setup
echo ================================
echo.

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.9-3.11 from https://python.org
    echo Make sure to tick "Add Python to PATH" during install.
    pause
    exit /b
)

:: Warn if Python 3.12+
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo Found Python %PYVER%
echo %PYVER% | findstr /r "^3\.12\." >nul
if not errorlevel 1 (
    echo.
    echo WARNING: Python 3.12 detected. MediaPipe requires Python 3.9-3.11.
    echo Download Python 3.11 from https://python.org/downloads
    pause
    exit /b
)

echo.
echo Creating virtual environment...
python -m venv venv

echo Activating...
call venv\Scripts\activate.bat

echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

echo.
echo ================================
echo  Setup complete!
echo  Run the tracker with:
echo    venv\Scripts\activate
echo    python hand_tracker.py
echo ================================
pause
