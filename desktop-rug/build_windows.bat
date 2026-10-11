@echo off
rem Native Windows build: produces dist\windows\DesktopRug.exe
rem Requires Python 3.10-3.12 (x64) from python.org on PATH.
cd /d "%~dp0"
if not exist .venv (py -3 -m venv .venv || python -m venv .venv)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-windows.txt pyinstaller || exit /b 1
pyinstaller --noconfirm --clean --distpath dist\windows --workpath build\windows packaging\desktop-rug.spec || exit /b 1
echo.
echo Built: dist\windows\DesktopRug.exe
