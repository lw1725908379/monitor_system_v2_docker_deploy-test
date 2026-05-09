@echo off
chcp 65001 >nul
title MonitorSystem V1.2 - 停止服务

echo ========================================
echo   MonitorSystem V1.2 - 停止中...
echo ========================================

REM 查找并结束 Python 进程（只结束运行 run_server.py 的进程）
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8888" ^| findstr "LISTENING"') do (
    echo [信息] 正在终止进程 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

REM 如果上述方法没找到，尝试直接结束 python.exe
tasklist /FI "IMAGENAME eq python.exe" 2>nul | findstr /I "python.exe" >nul
if not errorlevel 1 (
    echo [提示] 尝试结束所有 Python 进程...
    taskkill /F /IM python.exe >nul 2>&1
)

echo.
echo ========================================
echo   服务已停止!
echo ========================================
echo.
timeout /t 2 /nobreak >nul
