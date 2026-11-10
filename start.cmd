@echo off
cd /d "%~dp0"
if exist "dist-v1.1.1\HoverTranslate\HoverTranslate.exe" (
    start "" "dist-v1.1.1\HoverTranslate\HoverTranslate.exe"
    exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "main.py"
    exit /b
)
echo Please run setup.ps1 first, or use the packaged executable.
pause
