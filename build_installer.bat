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

if exist ".venv\Scripts\activate.bat" (
    set "VENV_PATH=.venv"
) else if exist "venv_win\Scripts\activate.bat" (
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

where uv >nul 2>nul
if errorlevel 1 (
    echo.
    echo ERROR: 'uv' was not found on PATH.
    echo Install from https://docs.astral.sh/uv/ then retry.
    goto :error_exit
)

rem Bump the app version (default: patch) before building so the installer and
rem Kiwiscribe.py carry the new number. Override with: build_installer.bat minor
rem Skip the bump with: build_installer.bat nobump
set "VERSION_PART=%~1"
if "%VERSION_PART%"=="" set "VERSION_PART=patch"
if /I "%VERSION_PART%"=="nobump" (
    echo Keeping current app version [nobump]...
) else (
    echo Bumping app version [%VERSION_PART%]...
)
for /f "usebackq delims=" %%V in (`"%PYTHON_EXE%" bump_version.py %VERSION_PART%`) do set "NEW_VERSION=%%V"
if not defined NEW_VERSION (
    echo.
    echo ERROR: Failed to resolve app version.
    goto :error_exit
)
echo App version for this build is %NEW_VERSION%

echo Verifying pynsist installation...
"%PYTHON_EXE%" -c "import nsist" >nul 2>nul
if errorlevel 1 (
    echo pynsist not found. Installing it now...
    uv pip install pynsist --python "%PYTHON_EXE%"
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
    uv pip install pillow --python "%PYTHON_EXE%"
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

rem uv has no 'pip download'; bootstrap pip only for fetching installer wheels.
echo Ensuring pip is available for wheel download...
"%PYTHON_EXE%" -c "import pip" >nul 2>nul
if errorlevel 1 (
    uv pip install pip --python "%PYTHON_EXE%"
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install pip into the virtual environment.
        goto :error_exit
    )
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

rem Publish the installer as a GitHub Release asset so users can download it
rem without cloning the repo. Only the version bump files are committed/pushed
rem (not other pending local changes).
call :publish_github_release
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

:publish_github_release
echo.
echo ----------------------------------------
echo Publishing installer to GitHub Releases
echo ----------------------------------------

set "INSTALLER_FILE=build\nsis\Kiwiscribe-%NEW_VERSION%-win64.exe"
if not exist "%INSTALLER_FILE%" (
    set "INSTALLER_FILE="
    for %%F in ("build\nsis\*.exe") do set "INSTALLER_FILE=%%~fF"
)
if not defined INSTALLER_FILE (
    echo WARNING: Installer .exe not found for GitHub release upload.
    goto :eof
)
for %%F in ("%INSTALLER_FILE%") do set "INSTALLER_FILE=%%~fF"

where gh >nul 2>nul
if errorlevel 1 (
    echo WARNING: GitHub CLI ^(gh^) not found. Installer was built but not published.
    echo Install from https://cli.github.com/ then run: gh auth login
    goto :eof
)

gh auth status >nul 2>nul
if errorlevel 1 (
    echo WARNING: gh is not authenticated. Installer was built but not published.
    echo Run: gh auth login
    goto :eof
)

set "RELEASE_TAG=v%NEW_VERSION%"

echo Committing version bump ^(Kiwiscribe.py, kiwiscribe_installer.cfg^)...
git add -- "Kiwiscribe.py" "kiwiscribe_installer.cfg"
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "release: Kiwiscribe %NEW_VERSION%"
    if errorlevel 1 (
        echo WARNING: Failed to commit version bump. Continuing with release publish...
    ) else (
        echo Pushing version bump to origin...
        git push origin HEAD
        if errorlevel 1 (
            echo WARNING: git push failed. The release tag may point at an older commit.
        )
    )
) else (
    echo No pending version-file changes to commit.
)

echo Publishing GitHub release %RELEASE_TAG% with:
echo   %INSTALLER_FILE%

gh release view "%RELEASE_TAG%" >nul 2>nul
if errorlevel 1 (
    gh release create "%RELEASE_TAG%" "%INSTALLER_FILE%" --title "Kiwiscribe %NEW_VERSION%" --generate-notes
) else (
    echo Release %RELEASE_TAG% already exists. Updating installer asset...
    gh release upload "%RELEASE_TAG%" "%INSTALLER_FILE%" --clobber
)
if errorlevel 1 (
    echo WARNING: Failed to publish GitHub release %RELEASE_TAG%.
    echo Local installer is still available at:
    echo   %INSTALLER_FILE%
    goto :eof
)

echo.
echo GitHub release published successfully: %RELEASE_TAG%
for /f "usebackq delims=" %%U in (`gh release view "%RELEASE_TAG%" --json url -q .url 2^>nul`) do (
    echo Release URL: %%U
)
goto :eof
