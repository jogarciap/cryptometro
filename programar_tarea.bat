@echo off
REM Registra una tarea diaria en el Programador de tareas de Windows.
REM Uso: programar_tarea.bat            (todos los dias a las 09:00)
REM      programar_tarea.bat 07:30      (a la hora que indiques, formato HH:MM)
cd /d "%~dp0"
set HORA=%1
if "%HORA%"=="" set HORA=09:00
schtasks /Create /F /SC DAILY /ST %HORA% /TN "InvestigadorCripto" /TR "\"%~dp0ejecutar.bat\""
if %errorlevel%==0 (
    echo Tarea "InvestigadorCripto" programada todos los dias a las %HORA%.
    echo Para probarla ahora:   schtasks /Run /TN "InvestigadorCripto"
    echo Para borrarla:         schtasks /Delete /TN "InvestigadorCripto" /F
)
pause
