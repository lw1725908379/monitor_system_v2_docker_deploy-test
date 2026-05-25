@echo off
chcp 65001 >nul
title MonitorSystem V1.3 - Stopping Service

echo ========================================
echo   MonitorSystem V1.3 - Stopping...
echo ========================================

REM Find and kill Python process on port 8888
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8888" ^| findstr "LISTENING"') do (
    echo [INFO] Terminating process PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

REM If not found, try killing all python.exe
tasklist /FI "IMAGENAME eq python.exe" 2>nul | findstr /I "python.exe" >nul
if not errorlevel 1 (
    echo [INFO] Killing all Python processes...
    taskkill /F /IM python.exe >nul 2>&1
)

echo.
echo ========================================
echo   Service Stopped!
echo ========================================
echo.
timeout /t 2 /nobreak >nul
