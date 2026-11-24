@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto python_missing
py -3.12 -V >nul 2>nul
if errorlevel 1 goto python_missing
py -3.12 -m scripts.orion_bootstrap --open %*
if errorlevel 1 goto failed
exit /b 0
:python_missing
echo Python 3.12 est requis. Installez-le avec py install 3.12 ou depuis python.org.
pause
exit /b 1
:failed
pause
exit /b 1
