@echo off
chcp 65001 >nul
setlocal EnableExtensions
title Desktop Rug - Enable
rem Desktop Rug - ENABLE: install for this user, start with Windows, start now.
rem No administrator rights needed (per-user install + HKCU Run key).
set "HERE=%~dp0"
set "DST_DIR=%LOCALAPPDATA%\DesktopRug"
set "DST=%DST_DIR%\DesktopRug.exe"
set "SRC="
if exist "%HERE%DesktopRug.exe" set "SRC=%HERE%DesktopRug.exe"
if not defined SRC if exist "%DST%" set "SRC=%DST%"
if not defined SRC goto notfound

echo Enabling Desktop Rug ...
rem 1) the app copies itself to %LOCALAPPDATA%\DesktopRug and registers autostart
start "" /wait "%SRC%" --enable-autostart
rem 2) belt and braces, in case step 1 could not run
if not exist "%DST_DIR%" mkdir "%DST_DIR%"
if not exist "%DST%" copy /y "%SRC%" "%DST%" >nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v DesktopRug /t REG_SZ /d "\"%DST%\" --autostart" /f >nul
rem 3) start it now (a second copy never runs twice; it only shows the running one)
start "" "%DST%"
echo.
echo Desktop Rug is ENABLED. It is running now and will start after every restart.
echo To turn it off, run Disable-DesktopRug.bat
timeout /t 4 >nul 2>&1 || ping -n 4 127.0.0.1 >nul
exit /b 0

:notfound
echo DesktopRug.exe was not found next to this file.
echo Keep this .bat in the same folder as DesktopRug.exe and run it again.
pause
exit /b 1
