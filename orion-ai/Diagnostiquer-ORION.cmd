@echo off
cd /d "%~dp0"
py -3.12 -m scripts.orion_doctor %*
set "ORION_DOCTOR_EXIT=%ERRORLEVEL%"
pause
exit /b %ORION_DOCTOR_EXIT%
