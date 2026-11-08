@echo off
rem AllForOne - genera dist\AllForOne\AllForOne.exe (standalone) y el ZIP de distribucion.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\package.ps1" %*
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Distribucion lista en dist\AllForOne) else (echo El empaquetado fallo. Revisa la carpeta logs\)
pause
exit /b %RC%
