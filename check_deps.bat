@echo off
echo Running Kiwiscribe Dependency Check...
echo.

REM Activate the virtual environment
call .\\venv\\Scripts\\activate.bat

REM Run the dependency manager to check for conflicts
python dependency_manager.py check

echo.
echo Check complete.
pause
