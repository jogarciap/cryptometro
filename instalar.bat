@echo off
REM Crea el entorno virtual e instala las dependencias. Se ejecuta una sola vez.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo No se pudo crear el entorno. Instala Python 3.11 o superior desde python.org
    echo y marca la casilla "Add python.exe to PATH".
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if not exist ".env" copy ".env.example" ".env" >nul
echo.
echo Instalacion terminada. Ahora ejecuta: ejecutar.bat
pause
