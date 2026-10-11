@echo off
chcp 65001 >nul
setlocal EnableExtensions
title Desktop Rug - Disable
rem Desktop Rug - DISABLE: close it and stop it starting with Windows.
rem Rug position, design and settings are kept.
set "HERE=%~dp0"
set "DST=%LOCALAPPDATA%\DesktopRug\DesktopRug.exe"
set "EXE="
if exist "%DST%" set "EXE=%DST%"
if not defined EXE if exist "%HERE%DesktopRug.exe" set "EXE=%HERE%DesktopRug.exe"

echo Disabling Desktop Rug ...
rem 1) ask the app to save, quit and remove its autostart entry
if defined EXE start "" /wait "%EXE%" --disable-autostart --quit-running
rem 2) belt and braces
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v DesktopRug /f >nul 2>&1
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Desktop Rug.lnk" >nul 2>&1
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DesktopRug.lnk" >nul 2>&1
taskkill /im DesktopRug.exe /f >nul 2>&1
echo.
echo Desktop Rug is DISABLED. It is closed and will not start with Windows any more.
echo Your settings are kept. To turn it back on, run Enable-DesktopRug.bat
timeout /t 4 >nul 2>&1 || ping -n 4 127.0.0.1 >nul
exit /b 0
