# Kiwiscribe Executable Build Instructions

This guide will help you create an executable (.exe) file from your Kiwiscribe
Python application with a custom icon and no terminal window.

## Prerequisites

1. **Python 3.13** installed on your system
2. **Virtual environment** (recommended)
3. **All dependencies** installed

## Quick Start

### Option 1: Automated Build (Recommended)

Simply double-click `build_exe.bat` or run it from command prompt:

```cmd
build_exe.bat
```

This script will:

- Check and install PyInstaller if needed
- Activate your virtual environment automatically
- Clean previous builds
- Build the executable
- Move the final .exe to your current directory

### Option 2: Manual Build

1. **Install PyInstaller** (if not already installed):

   ```cmd
   pip install pyinstaller
   ```

2. **Install all dependencies**:

   ```cmd
   pip install -r requirements_build.txt
   ```

3. **Build the executable**:

   ```cmd
   pyinstaller Kiwiscribe.spec
   ```

4. **Find your executable** in the `dist` folder:

    ```text
    dist/Kiwiscribe.exe
    ```

## What's Included in the Executable

- ✅ **Custom Icon**: Uses `TranscribeAppIconSquare.ico`
- ✅ **No Terminal Window**: Runs in windowed mode only
- ✅ **All Dependencies**: Includes PyQt6, AI libraries, PDF processing, etc.
- ✅ **Single File**: Everything bundled into one executable

## Key Features of the Build Configuration

### Icon Configuration

- **File**: `TranscribeAppIconSquare.ico`
- **Location**: Must be in the same directory as the spec file
- **Format**: Windows ICO format

### Window Mode

- **Console**: `False` - No terminal/command prompt window
- **Mode**: Windowed GUI application only

### Dependencies Included

- PyQt6 (GUI framework)
- AssemblyAI, OpenAI, Anthropic, Google Gemini APIs
- Soniox async transcription (REST via requests)
- PDF processing (PyPDF2, pypdf)
- HTTP requests and utilities
- Windows registry access (winreg)

### Optimizations

- **UPX Compression**: Enabled to reduce file size
- **Excluded Libraries**: Removes unused packages (tkinter, matplotlib, etc.)
- **Hidden Imports**: Explicitly includes all required modules

## Troubleshooting

### Common Issues and Solutions

1. **"Icon file not found"**

   - Ensure `TranscribeAppIconSquare.ico` is in the same directory
   - Check the file isn't corrupted

2. **"Module not found" errors**

   - Install missing dependencies: `pip install -r requirements_build.txt`
   - Activate your virtual environment first

3. **Large file size**

   - The executable will be large (~200-500MB) due to AI libraries
   - This is normal for applications with many dependencies

4. **Build fails with virtual environment**

   - Make sure you're in the correct virtual environment
   - Try: `venv_win\Scripts\activate.bat`

5. **Application doesn't start**

   - Check Windows Defender/antivirus isn't blocking it
   - Try running as administrator
   - Check the build log for missing dependencies

### Manual Debugging

If the automated build fails, you can debug manually:

```cmd
# Activate virtual environment
venv_win\Scripts\activate.bat

# Install PyInstaller
pip install pyinstaller

# Build with verbose output
pyinstaller --log-level=DEBUG Kiwiscribe.spec
```

## File Structure After Build

```text
Your Project Directory/
├── Kiwiscribe.py           # Source code
├── Kiwiscribe.spec         # PyInstaller configuration
├── TranscribeAppIconSquare.ico  # Icon file
├── build_exe.bat           # Automated build script
├── requirements_build.txt  # Dependencies
├── BUILD_INSTRUCTIONS.md   # This file
└── Kiwiscribe.exe         # Final executable (after build)
```

## Testing the Executable

1. **Run the executable**: Double-click `Kiwiscribe.exe`
2. **Check the icon**: Should display your custom icon in taskbar/window
3. **Verify no terminal**: No command prompt window should appear
4. **Test functionality**: Try the main features of your application

## Distribution

The final `Kiwiscribe.exe` file is completely standalone and can be:

- Copied to other Windows computers
- Distributed without requiring Python installation
- Run directly without any setup

## Notes

- **File Size**: The executable will be large due to bundled dependencies
- **Startup Time**: First launch may be slower as files are extracted
- **Antivirus**: Some antivirus software may flag PyInstaller executables
- **Updates**: Rebuild the executable when you update your Python code

### Cross-Platform Dependency Update Reminder

- Windows workflow in this repo uses `venv_win` and `update_deps_win.bat`.
- When working from Linux, create a separate Linux virtual environment (for example, `.venv_linux`) and a dedicated update script (for example, `update_deps_linux.sh`).
- Do not share one virtual environment between Windows and Linux.

## Support

If you encounter issues:

1. Check the build log output
2. Verify all dependencies are installed
3. Ensure the icon file exists and is valid
4. Try building in a clean virtual environment
