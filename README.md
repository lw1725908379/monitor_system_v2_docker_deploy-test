# MonitorSystem V1.3

设备监控系统，用于远程监控 Linux 嵌入式设备。

## 功能特性

- **设备监控**：CPU、内存、进程、温度、网络监控
- **告警管理**：多种告警类型，支持邮件通知
- **温度测试**：支持常温基准测试和高温压力测试
- **内存分析**：趋势分析、泄漏检测、Ridge回归ML预测、统计报表
- **自动清理**：自动清理离线设备（超过3天）
- **开机自启**：支持 Windows 计划任务开机自动运行

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | HTML + Bootstrap 5 + Font Awesome |
| 后端 | Python Flask + Waitress |
| 数据库 | SQLite (WAL模式) |
| 远程连接 | Paramiko (SSH) |
| 任务调度 | APScheduler |
| 机器学习 | NumPy + scikit-learn (Ridge回归) |

## 部署指南（Windows）

### 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows Server 2016+ / Windows 10+ |
| Python | 3.9+ |
| 网络 | 可访问目标监控设备 |

### 步骤 1：安装 Python

1. 下载 Python 3.9+：[https://www.python.org/downloads/](https://www.python.org/downloads/)
2. **务必勾选** `Add Python to PATH`
3. 验证安装：
```cmd
python --version
```

### 步骤 2：复制项目

将项目文件夹复制到目标服务器（如 `C:\MonitorSystem`）

### 步骤 3：安装依赖

```cmd
cd C:\MonitorSystem
pip install -r requirements.txt
```

### 步骤 4：配置防火墙

```cmd
netsh advfirewall firewall add rule name="MonitorSystem" dir=in action=allow protocol=tcp localport=8888
```

### 步骤 5：安装开机自启（可选）

右键 `deploy\install_service.bat` → **以管理员身份运行**

### 步骤 6：启动服务

双击 `deploy\start.bat`

### 访问地址

```
http://localhost:8888
```

## 常用操作

| 操作 | 命令 |
|------|------|
| 启动服务 | `deploy\start.bat` |
| 停止服务 | `deploy\stop.bat` |
| 安装自启 | `deploy\install_service.bat` (管理员) |
| 卸载自启 | `deploy\uninstall_service.bat` (管理员) |

## 更改端口

编辑 `backend\port.txt`，修改里面的数字后保存，重启服务。

## 目录结构

```
C:\MonitorSystem\
├── backend\              # 后端代码
│   ├── app\            # 应用模块
│   ├── run_server.py   # 服务入口
│   └── port.txt        # 端口配置
├── frontend\            # 前端页面
├── storage\            # 数据存储
├── logs\              # 日志目录
├── deploy\            # 部署脚本
│   ├── start.bat
│   ├── stop.bat
│   ├── install_service.bat
│   └── uninstall_service.bat
├── DEPLOY_WINDOWS.md  # 部署指南
├── requirements.txt   # Python依赖
├── docker-compose.yml # Docker配置
└── Dockerfile        # Docker镜像
```

## 部署指南（Docker）

```bash
# 启动服务
docker-compose up -d

# 访问地址
http://localhost:8080
```

## 配置说明

### 监控配置 (backend/app/core/config.py)

```python
MONITOR_CONFIG = {
    'memory_threshold': 95,    # 内存告警阈值 (%)
    'cpu_threshold': 95,       # CPU告警阈值 (%)
    'check_interval': 30,      # 检查间隔 (秒)
    'auto_process_threshold': 30.0,  # 风险进程阈值
}

# 设备清理配置
DEVICE_CLEANUP_CONFIG = {
    'offline_days_threshold': 3,   # 离线超过3天自动清理
    'enabled': True,
}
```

### 邮件配置

```python
EMAIL_CONFIG = {
    'smtp_server': 'smtp.qq.com',
    'smtp_port': 587,
    'sender': 'your_email@qq.com',
    'password': 'your_password',
    'receivers': ['receiver@example.com'],
}
```

### ML模型配置 (Ridge回归)

```python
ML_MODEL_CONFIG = {
    'ridge_alpha': 1.0,           # 正则化参数
    'analysis_days': 7,           # 分析历史天数
    'prediction_steps': 120,      # 预测步数(30秒/步，120=1小时)
    'min_data_points': 50,        # 最少数据点
    'safety_margin': {            # 安全边际(%)
        'stable': 5,              # 稳定趋势
        'up': 10,                 # 上升趋势
        'leak': 15,               # 泄漏趋势
    },
    'trend_threshold': {           # 趋势判断(MB/小时)
        'leak': 1.0,
        'down': -1.0,
    }
}
```

## 定时任务

| 任务 | 时间 | 说明 |
|------|------|------|
| 设备监控 | 每30秒 | 检查所有设备状态 |
| 内存分析 | 每天 02:00 | 分析进程内存趋势 |
| 数据备份 | 每天 03:00 | 自动备份数据 |
| 存储管理 | 每天 04:00 | 清理日志和历史数据 |
| 离线清理 | 每天 04:30 | 清理离线设备 |

## 版本信息

- **版本**：V1.3
- **构建时间**：自动获取
- **更新内容**：引入Ridge回归ML模型优化推荐阈值计算

## 许可证

MIT License
