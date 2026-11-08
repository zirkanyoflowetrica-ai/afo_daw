@echo off
rem AllForOne - prepara el entorno, compila el motor C++, prueba e inicia la aplicacion.
rem Registro completo en logs\build_*.log
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build.ps1" -Run %*
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo La compilacion o las pruebas fallaron. Revisa la carpeta logs\
  pause
)
exit /b %RC%
