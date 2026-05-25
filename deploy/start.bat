@echo off
chcp 65001 >nul
title MonitorSystem V1.3 Launcher

cd /d "%~dp0.."

echo ========================================
echo   MonitorSystem V1.3 - Starting...
echo ========================================

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.9+
    pause
    exit /b 1
)

REM Check dependencies
pip show flask >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    pip install -r requirements.txt
)

REM Read port config (default 8888)
set PORT=8888
if exist "backend\port.txt" (
    set /p PORT=<"backend\port.txt"
)

echo [INFO] Using port: %PORT%
echo [INFO] Starting service...

REM Start Python service in background
start /b python backend\run_server.py --port=%PORT% 2>>logs\startup.log

REM Wait for service to start
timeout /t 3 /nobreak >nul

REM Check if process started successfully
tasklist /FI "IMAGENAME eq python.exe" 2>nul | findstr /I "python.exe" >nul
if errorlevel 1 (
    echo [ERROR] Service failed to start. Check logs\startup.log
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Service Started!
echo   Access: http://localhost:%PORT%
echo ========================================
echo.
echo Press any key to close this window (service will continue running)...
pause >nul
