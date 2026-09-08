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
echo   - Ingest window: HerpMonitor - Ingest
echo   - Sensor plugin window: HerpMonitor - Sensor Plugin (Govee)
echo   - Plug plugin window: HerpMonitor - Plug Plugin (Tuya)
echo Close any window to stop that part. Closing this window is fine ^-^- it's done its job.
echo.

start "HerpMonitor - Website" cmd /k "call .venv\Scripts\activate.bat && python -u -m uvicorn web.main:app --host 127.0.0.1 --port 22255"
start "HerpMonitor - Ingest" cmd /k "call .venv\Scripts\activate.bat && python -u ingest\ingest.py"
start "HerpMonitor - Sensor Plugin (Govee)" cmd /k "call .venv\Scripts\activate.bat && python -u plugins\govee_ble\plugin.py"
start "HerpMonitor - Plug Plugin (Tuya)" cmd /k "call .venv\Scripts\activate.bat && python -u plugins\tuya_lan\plugin.py"

rem Give the website a moment to come up before opening the browser to it.
timeout /t 3 /nobreak >nul
start "" "http://localhost:22255"

echo HerpMonitor is running in the four new windows.
pause
