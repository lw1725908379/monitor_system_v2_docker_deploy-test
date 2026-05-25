@echo off
chcp 65001 >nul
title MonitorSystem V1.3 - Uninstall Auto-Start

echo ========================================
echo   MonitorSystem V1.3 - Uninstall Auto-Start
echo ========================================

REM Check if task exists
schtasks /Query /TN "MonitorSystem_AutoStart" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Auto-start not installed, nothing to uninstall
    pause
    exit /b 0
)

REM Delete scheduled task
echo [INFO] Deleting scheduled task...
schtasks /Delete /TN "MonitorSystem_AutoStart" /F >nul 2>&1

if errorlevel 1 (
    echo [ERROR] Failed to delete task
    echo Please run as Administrator
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Auto-Start Uninstalled!
echo ========================================
echo.
pause
