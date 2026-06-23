@echo off
setlocal

echo ========================================
echo Building Kiwiscribe Windows Installer
echo ========================================

rem Default to failure; only the verified-success path sets this to 0.
set "BUILD_RC=1"
set "PYTHON_EXE=python"
set "VENV_PATH="
set "ICON_SRC=KiwiScribeSquared.png"
set "ICON_OUT=KiwiScribeSquared.ico"

if exist "venv_win\Scripts\activate.bat" (
    set "VENV_PATH=venv_win"
) else if exist "venv\Scripts\activate.bat" (
    set "VENV_PATH=venv"
) else if exist "venv2\Scripts\activate.bat" (
    set "VENV_PATH=venv2"
) else if exist "venv_local\Scripts\activate.bat" (
    set "VENV_PATH=venv_local"
)

if defined VENV_PATH (
    echo Activating virtual environment from '%VENV_PATH%'...
    call "%VENV_PATH%\Scripts\activate.bat"
    set "PYTHON_EXE=%VENV_PATH%\Scripts\python.exe"
) else (
    echo No virtual environment found. Using system Python.
)

rem Bump the app version (default: patch) before building so the installer and
rem Kiwiscribe.py carry the new number. Override with: build_installer.bat minor
set "VERSION_PART=%~1"
if "%VERSION_PART%"=="" set "VERSION_PART=patch"
echo Bumping app version (%VERSION_PART%)...
for /f "usebackq delims=" %%V in (`"%PYTHON_EXE%" bump_version.py %VERSION_PART%`) do set "NEW_VERSION=%%V"
if not defined NEW_VERSION (
    echo.
    echo ERROR: Failed to bump app version.
    goto :error_exit
)
echo New app version is %NEW_VERSION%

echo Verifying pynsist installation...
"%PYTHON_EXE%" -c "import nsist" >nul 2>nul
if errorlevel 1 (
    echo pynsist not found. Installing it now...
    "%PYTHON_EXE%" -m pip install pynsist
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install pynsist.
        goto :error_exit
    )
)

if exist "installer_wheels" rmdir /s /q "installer_wheels"
mkdir "installer_wheels"

if not exist "%ICON_SRC%" (
    echo.
    echo ERROR: Icon source image not found: %ICON_SRC%
    goto :error_exit
)

echo Verifying Pillow for icon generation...
"%PYTHON_EXE%" -c "from PIL import Image" >nul 2>nul
if errorlevel 1 (
    echo Pillow not found. Installing it now...
    "%PYTHON_EXE%" -m pip install pillow
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install Pillow.
        goto :error_exit
    )
)

echo Generating installer icon from %ICON_SRC%...
"%PYTHON_EXE%" generate_installer_icon.py "%ICON_SRC%" "%ICON_OUT%"
if errorlevel 1 (
    echo.
    echo ERROR: Failed to generate installer icon.
    goto :error_exit
)

echo Downloading runtime wheels...
"%PYTHON_EXE%" -m pip download --only-binary=:all: -r requirements_installer.txt -d installer_wheels
if errorlevel 1 (
    echo.
    echo ERROR: Failed to download installer wheels.
    goto :error_exit
)

if exist "build\nsis" rmdir /s /q "build\nsis"

echo Running pynsist...
"%PYTHON_EXE%" -m nsist kiwiscribe_installer.cfg
if errorlevel 1 (
    echo.
    echo ERROR: pynsist failed to build the installer.
    goto :error_exit
)

rem pynsist returns 0 even when its makensis subprocess fails (e.g. "Bad text
rem encoding"), so confirm the installer .exe was actually produced. build\nsis is
rem wiped before this run, so any .exe present here is from the current build.
echo Verifying installer output...
if not exist "build\nsis\*.exe" (
    echo.
    echo ERROR: No installer .exe was produced in build\nsis.
    echo makensis likely failed - check the output above ^(e.g. "Bad text encoding"^).
    goto :error_exit
)

echo.
echo ========================================
echo INSTALLER BUILD SUCCESSFUL!
echo ========================================
echo Installer output is in build\nsis
set "BUILD_RC=0"
goto :cleanup

:error_exit
echo.
echo Installer build aborted due to an error.
set "BUILD_RC=1"

:cleanup
if exist "installer_wheels" rmdir /s /q "installer_wheels"

echo.
echo Press any key to exit...
pause >nul
endlocal & exit /b %BUILD_RC%