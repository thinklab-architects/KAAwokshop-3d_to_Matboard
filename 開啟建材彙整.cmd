@echo off
chcp 65001 >nul
rem Double-click to start the server (if needed) and open the site.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start.ps1"
if errorlevel 1 pause
