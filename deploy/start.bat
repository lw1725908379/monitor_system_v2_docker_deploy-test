@echo off
chcp 65001 >nul
title MonitorSystem V1.2 启动器

cd /d "%~dp0.."

echo ========================================
echo   MonitorSystem V1.2 - 启动中...
echo ========================================

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

REM 检查依赖是否已安装
pip show flask >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装依赖...
    pip install -r requirements.txt
)

REM 读取端口配置（默认为 8888）
set PORT=8888
if exist "backend\port.txt" (
    set /p PORT=<"backend\port.txt"
)

echo [信息] 使用端口: %PORT%
echo [信息] 启动服务...

REM 后台启动 Python 服务
start /b python backend\run_server.py --port=%PORT% 2>>logs\startup.log

REM 等待几秒让服务启动
timeout /t 3 /nobreak >nul

REM 检查进程是否启动成功
tasklist /FI "IMAGENAME eq python.exe" 2>nul | findstr /I "python.exe" >nul
if errorlevel 1 (
    echo [错误] 服务启动失败，请查看 logs\startup.log
    pause
    exit /b 1
)

echo.
echo ========================================
echo   服务已启动!
echo   访问地址: http://localhost:%PORT%
echo ========================================
echo.
echo 按任意键关闭此窗口（服务将继续在后台运行）...
pause >nul
