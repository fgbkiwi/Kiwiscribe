@echo off
echo Activating local Python virtual environment...
if not exist ".\.venv\Scripts\activate.bat" (
	echo [ERROR] Virtual environment not found at .\.venv\Scripts\activate.bat
	echo Create it first, for example: uv venv .venv --python 3.13
	exit /b 1
)
call .\.venv\Scripts\activate.bat
echo.
echo Virtual environment activated! You can now run Python commands.
echo Type 'deactivate' to exit the virtual environment.
echo.
cmd /k
