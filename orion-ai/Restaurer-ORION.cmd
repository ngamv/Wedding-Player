@echo off
cd /d "%~dp0"
py -3.12 -m scripts.orion_recovery %*
if errorlevel 1 pause
