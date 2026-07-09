@echo off
rem Stop Auto Chat Studio (kills whatever is listening on port 8008).
title Auto Chat Studio Stopper
set FOUND=

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8008 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>nul && set FOUND=1
)

if defined FOUND (
    echo Auto Chat Studio stopped.
) else (
    echo Nothing running on port 8008.
)
timeout /t 2 /nobreak >nul
exit /b 0
