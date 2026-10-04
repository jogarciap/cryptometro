@echo off
REM Genera el reporte del dia. Acepta los mismos argumentos que run.py (--no-abrir, --verificar).
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py %*
