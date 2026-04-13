@echo off
echo Running Kiwiscribe Safe Dependency Update...
echo.

REM Activate the virtual environment
call .\\venv\\Scripts\\activate.bat

REM Run the dependency manager to update packages
python dependency_manager.py update

echo.
echo Update process finished.
pause
