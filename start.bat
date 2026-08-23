@echo off
setlocal

rem Always run relative to this script's own folder, no matter where it's launched from.
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo Python virtual environment not found ^(.venv^).
    echo Run the one-time setup steps in docs\USER_GUIDE.md first, then try again.
    echo.
    pause
    exit /b 1
)

echo Starting HerpMonitor...
echo   - Website window: HerpMonitor - Website
echo   - Sensor listener window: HerpMonitor - Sensor Listener
echo   - Plug listener window: HerpMonitor - Plug Listener
echo Close any window to stop that part. Closing this window is fine ^-^- it's done its job.
echo.

start "HerpMonitor - Website" cmd /k "call .venv\Scripts\activate.bat && python -u -m uvicorn web.main:app --host 127.0.0.1 --port 22255"
start "HerpMonitor - Sensor Listener" cmd /k "call .venv\Scripts\activate.bat && python -u collectors\govee_collector.py"
start "HerpMonitor - Plug Listener" cmd /k "call .venv\Scripts\activate.bat && python -u collectors\tuya_collector.py"

rem Give the website a moment to come up before opening the browser to it.
timeout /t 3 /nobreak >nul
start "" "http://localhost:22255"

echo HerpMonitor is running in the three new windows.
pause
