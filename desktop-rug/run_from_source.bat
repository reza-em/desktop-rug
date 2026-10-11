@echo off
rem Run Desktop Rug from source on Windows (Python 3.10+ x64 required).
cd /d "%~dp0"
if not exist .venv (py -3 -m venv .venv || python -m venv .venv)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
start "" .venv\Scripts\pythonw.exe -m desktop_rug %*
