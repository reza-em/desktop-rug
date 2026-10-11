@echo off
chcp 65001 >nul
setlocal EnableExtensions
title Desktop Rug - Uninstall
rem Desktop Rug - UNINSTALL: disable, close, remove the installed copy AND the settings.
set "HERE=%~dp0"
set "DST=%LOCALAPPDATA%\DesktopRug\DesktopRug.exe"
echo This removes Desktop Rug and its settings from this user account.
choice /c YN /m "Continue"
if errorlevel 2 exit /b 0
set "EXE="
if exist "%HERE%DesktopRug.exe" set "EXE=%HERE%DesktopRug.exe"
if not defined EXE if exist "%DST%" set "EXE=%DST%"
if defined EXE start "" /wait "%EXE%" --restore-wallpaper
if defined EXE start "" /wait "%EXE%" --uninstall
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v DesktopRug /f >nul 2>&1
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Desktop Rug.lnk" >nul 2>&1
taskkill /im DesktopRug.exe /f >nul 2>&1
timeout /t 2 >nul 2>&1 || ping -n 2 127.0.0.1 >nul
rmdir /s /q "%LOCALAPPDATA%\DesktopRug" >nul 2>&1
rmdir /s /q "%LOCALAPPDATA%\desktop-rug" >nul 2>&1
echo Desktop Rug has been removed.
timeout /t 4 >nul 2>&1 || ping -n 4 127.0.0.1 >nul
exit /b 0
