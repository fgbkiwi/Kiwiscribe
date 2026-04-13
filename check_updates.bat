@echo off
echo Checking for potential dependency conflicts before updating packages...
echo.

REM Activate the virtual environment
call .\venv\Scripts\activate.bat

REM Run the Python script to check for conflicts
python dependency_manager.py check

echo.
pause
