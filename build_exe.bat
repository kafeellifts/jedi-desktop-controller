@echo off
echo ================================
echo  Building Jedi Controller EXE
echo ================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    pause
    exit /b
)

python -m venv venv
call venv\Scripts\activate.bat

pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet

echo.
echo Building EXE (this takes a few minutes)...
echo.

for /f "delims=" %%i in ('python -c "import mediapipe, os; print(os.path.dirname(mediapipe.__file__))"') do set MP_PATH=%%i

pyinstaller --onefile ^
    --add-data "%MP_PATH%\modules;mediapipe/modules" ^
    --add-data "%MP_PATH%\python\solutions;mediapipe/python/solutions" ^
    --collect-data mediapipe ^
    --hidden-import mediapipe ^
    --hidden-import cv2 ^
    --hidden-import pyautogui ^
    --hidden-import pygrabber ^
    --name "JediController" ^
    hand_tracker.py

echo.
if exist dist\JediController.exe (
    echo ================================
    echo  Done!
    echo  EXE is at: dist\JediController.exe
    echo  Share that single file with anyone.
    echo ================================
) else (
    echo BUILD FAILED - check errors above.
)
pause
