@echo off
echo Running Kiwiscribe Dependency Check...
echo.

REM Activate the virtual environment
if not exist ".\venv_win\Scripts\activate.bat" (
	echo [ERROR] Virtual environment not found at .\venv_win\Scripts\activate.bat
	exit /b 1
)

call .\venv_win\Scripts\activate.bat
if errorlevel 1 (
	echo [ERROR] Failed to activate virtual environment.
	exit /b 1
)

REM Run the dependency manager to check for conflicts
python dependency_manager.py check
if errorlevel 1 (
	echo.
	echo [ERROR] Dependency check failed.
	exit /b 1
)

echo.
echo Check complete.
pause
