@echo off
rem Start Auto Chat Studio (web UI) and open it in the browser.
title Auto Chat Studio Launcher
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found in PATH. Install it from https://python.org and try again.
    pause
    exit /b 1
)

rem Install dependencies on first run
python -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo First run: installing dependencies...
    python -m pip install -r requirements.txt
)

echo Starting Auto Chat Studio at http://127.0.0.1:8008 ...
start "AutoChatStudio" /min python web_server.py

rem Give the server a moment, then open the browser
timeout /t 2 /nobreak >nul
start http://127.0.0.1:8008
exit /b 0
