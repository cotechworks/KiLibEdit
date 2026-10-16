@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m nuitka --mode=standalone --enable-plugin=tk-inter --windows-console-mode=disable --mingw64 --assume-yes-for-downloads --output-dir=dist --output-filename=KiLibEdit.exe --company-name=CoTechWorks --product-name=KiLibEdit --file-version=1.0.0.0 --product-version=1.0.0.0 --file-description="KiCad Symbol Library Table Editor" main.py
if errorlevel 1 goto :failed
echo Built: %~dp0dist\main.dist\KiLibEdit.exe
exit /b 0
:failed
echo Build failed.
pause
exit /b 1
