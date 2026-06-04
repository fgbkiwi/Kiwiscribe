@echo off
echo Running Kiwiscribe Safe Dependency Update...
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

REM Run the dependency manager to update packages
python dependency_manager.py update
if errorlevel 1 (
	echo.
	echo [ERROR] Dependency update failed.
	exit /b 1
)

echo.
echo Update process finished.
pause
