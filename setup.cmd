@echo off
chcp 65001 >nul
rem First run: creates .venv, installs dependencies, checks for SketchUpAPI.dll.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup.ps1" %*
pause
