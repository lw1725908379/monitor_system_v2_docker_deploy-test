@echo off
chcp 65001 >nul
title MonitorSystem V1.2 - 卸载开机自启

echo ========================================
echo   MonitorSystem V1.2 - 卸载开机自启
echo ========================================

REM 检查计划任务是否存在
schtasks /Query /TN "MonitorSystem_AutoStart" >nul 2>&1
if errorlevel 1 (
    echo [提示] 开机自启任务未安装，无需卸载
    pause
    exit /b 0
)

REM 删除计划任务
echo [信息] 正在删除计划任务...
schtasks /Delete /TN "MonitorSystem_AutoStart" /F >nul 2>&1

if errorlevel 1 (
    echo [错误] 删除计划任务失败
    echo 请以管理员身份运行此脚本
    pause
    exit /b 1
)

echo.
echo ========================================
echo   开机自启已卸载!
echo ========================================
echo.
pause
