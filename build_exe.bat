@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo       Zenith Launcher EXE Builder
echo ========================================

py -V >nul 2>&1
if not errorlevel 1 goto python_ok
echo ERROR: Python launcher (py) was not found.
echo Install Python 3.10 or newer from python.org and enable Add Python to PATH.
goto failed

:python_ok
echo.
echo Installing required packages...
py -m pip install --upgrade pip
if errorlevel 1 goto failed
py -m pip install PyQt6 minecraft-launcher-lib requests pyinstaller
if errorlevel 1 goto failed

echo.
echo Building ZenithLauncher.exe...
py -m PyInstaller --noconfirm --clean --onefile --windowed --name ZenithLauncher zenith_launcher.py
if errorlevel 1 goto failed

echo.
echo BUILD COMPLETE: dist\ZenithLauncher.exe
echo Upload that EXE to a GitHub Release for in-app updates to work.
pause
exit /b 0

:failed
echo.
echo BUILD FAILED. Read the error above.
pause
exit /b 1
