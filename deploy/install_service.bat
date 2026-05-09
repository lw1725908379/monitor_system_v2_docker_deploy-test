@echo off
chcp 65001 >nul
title MonitorSystem V1.2 - 安装开机自启

echo ========================================
echo   MonitorSystem V1.2 - 安装开机自启
echo ========================================

REM 获取脚本所在目录的绝对路径
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PROJECT_DIR=%SCRIPT_DIR%"

REM 检查计划任务是否存在，如果存在则先删除
schtasks /Query /TN "MonitorSystem_AutoStart" >nul 2>&1
if not errorlevel 1 (
    echo [提示] 任务已存在，正在删除旧任务...
    schtasks /Delete /TN "MonitorSystem_AutoStart" /F >nul 2>&1
)

REM 创建开机自启计划任务
echo [信息] 创建计划任务...
schtasks /Create /TN "MonitorSystem_AutoStart" ^
    /TR "\"%PROJECT_DIR%\deploy\start.bat\"" ^
    /SC ONSTART ^
    /RL HIGHEST ^
    /F >nul 2>&1

if errorlevel 1 (
    echo [错误] 创建计划任务失败
    echo 请以管理员身份运行此脚本
    pause
    exit /b 1
)

echo.
echo ========================================
echo   开机自启安装成功!
echo ========================================
echo.
echo 任务信息:
echo   - 任务名称: MonitorSystem_AutoStart
echo   - 触发器: 计算机启动时
echo   - 启动程序: %PROJECT_DIR%\deploy\start.bat
echo.
echo 您可以使用以下命令查看任务状态:
echo   schtasks /Query /TN "MonitorSystem_AutoStart"
echo.
pause
