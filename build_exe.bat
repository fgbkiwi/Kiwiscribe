@echo off
setlocal

echo ========================================
echo Building Kiwiscribe Executable
echo ========================================

REM --- Configuration ---
SET "PYTHON_EXE=python"
SET "VENV_PATH="

REM --- Find and Activate Virtual Environment ---
if exist "venv\Scripts\activate.bat" (
    SET "VENV_PATH=venv"
) else if exist "venv2\Scripts\activate.bat" (
    SET "VENV_PATH=venv2"
) else if exist "venv_local\Scripts\activate.bat" (
    SET "VENV_PATH=venv_local"
)

if defined VENV_PATH (
    echo Activating virtual environment from '%VENV_PATH%'...
    call "%VENV_PATH%\Scripts\activate.bat"
    SET "PYTHON_EXE=%VENV_PATH%\Scripts\python.exe"
) else (
    echo No virtual environment found. Using system Python.
)

REM --- Verify PyInstaller Installation ---
echo Checking for PyInstaller using '%PYTHON_EXE%'...
"%PYTHON_EXE%" -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo PyInstaller not found. Attempting to install...
    "%PYTHON_EXE%" -m pip install pyinstaller
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install PyInstaller.
        echo Please install it manually by running: "%PYTHON_EXE% -m pip install pyinstaller"
        goto :error_exit
    )
    echo PyInstaller installed successfully.
) else (
    echo PyInstaller is already installed.
)

REM --- Clean Previous Builds ---
echo Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "Kiwiscribe.exe" del "Kiwiscribe.exe"

REM --- Build the Executable ---
echo Building executable...
"%PYTHON_EXE%" -m PyInstaller Kiwiscribe.spec

if errorlevel 1 (
    goto :build_failed
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo Moving executable to the project directory...
move "dist\Kiwiscribe.exe" "Kiwiscribe.exe" >nul
echo.
echo Final executable: Kiwiscribe.exe
for %%A in (Kiwiscribe.exe) do echo File size: %%~zA bytes
echo.
goto :cleanup

:build_failed
echo.
echo ========================================
echo BUILD FAILED!
echo ========================================
echo PyInstaller encountered an error. Please check the messages above.
goto :cleanup

:error_exit
echo.
echo Build process aborted due to an error.

:cleanup
echo Cleaning up build artifacts...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo.
echo Press any key to exit...
pause >nul
endlocal
