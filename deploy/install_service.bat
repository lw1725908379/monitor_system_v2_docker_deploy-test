@echo off
chcp 65001 >nul
title MonitorSystem V1.3 - Install Auto-Start

echo ========================================
echo   MonitorSystem V1.3 - Install Auto-Start
echo ========================================

REM Get script directory
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PROJECT_DIR=%SCRIPT_DIR%"

REM Check if task exists, delete if so
schtasks /Query /TN "MonitorSystem_AutoStart" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Task exists, deleting old task...
    schtasks /Delete /TN "MonitorSystem_AutoStart" /F >nul 2>&1
)

REM Create scheduled task
echo [INFO] Creating scheduled task...
schtasks /Create /TN "MonitorSystem_AutoStart" ^
    /TR "\"%PROJECT_DIR%\deploy\start.bat\"" ^
    /SC ONSTART ^
    /RL HIGHEST ^
    /F >nul 2>&1

if errorlevel 1 (
    echo [ERROR] Failed to create task
    echo Please run as Administrator
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Auto-Start Installed!
echo ========================================
echo.
echo Task Info:
echo   - Task Name: MonitorSystem_AutoStart
echo   - Trigger: On System Startup
echo   - Program: %PROJECT_DIR%\deploy\start.bat
echo.
echo View task status:
echo   schtasks /Query /TN "MonitorSystem_AutoStart"
echo.
pause
