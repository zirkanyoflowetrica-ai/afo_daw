@echo off
rem AllForOne - elimina lo que los scripts anteriores crearon fuera de esta carpeta.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\limpiar_fuera.ps1"
exit /b %ERRORLEVEL%
