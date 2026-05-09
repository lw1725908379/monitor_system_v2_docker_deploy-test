# MonitorSystem V1.2 - Windows 部署指南

## 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows Server 2016+ 或 Windows 10+ |
| Python | 3.9 或更高版本 |
| 网络 | 可访问目标监控设备的网络 |

---

## 部署步骤

### 步骤 1: 安装 Python

1. 下载 Python 3.9+：[https://www.python.org/downloads/](https://www.python.org/downloads/)
2. 运行安装程序，**务必勾选** `Add Python to PATH`
3. 验证安装：
```cmd
python --version
pip --version
```

### 步骤 2: 复制项目文件

将项目文件夹复制到目标服务器，例如：`C:\MonitorSystem`

确保路径不包含中文或特殊字符。

### 步骤 3: 安装依赖

打开命令提示符（CMD），进入项目目录：

```cmd
cd C:\MonitorSystem
pip install -r requirements.txt
```

### 步骤 4: 配置防火墙

允许端口 8888 通过防火墙：

```cmd
netsh advfirewall firewall add rule name="MonitorSystem" dir=in action=allow protocol=tcp localport=8888
```

### 步骤 5: 安装开机自启（可选）

右键点击 `deploy\install_service.bat`，选择 **"以管理员身份运行"**

> 注意：安装开机自启需要管理员权限

### 步骤 6: 启动服务

双击运行 `deploy\start.bat`

首次启动会自动安装依赖并创建必要的目录。

---

## 使用说明

### 访问监控系统

打开浏览器访问：**http://localhost:8888**

### 常用操作

| 操作 | 操作方法 |
|------|----------|
| 启动服务 | 双击 `deploy\start.bat` |
| 停止服务 | 双击 `deploy\stop.bat` |
| 安装开机自启 | 右键 `deploy\install_service.bat` → 以管理员身份运行 |
| 卸载开机自启 | 右键 `deploy\uninstall_service.bat` → 以管理员身份运行 |
| 查看日志 | 使用文本编辑器打开 `logs` 目录下的日志文件 |

### 更改端口

如果需要更改端口号，编辑 `backend\port.txt` 文件，修改里面的数字后保存，然后重启服务。

---

## 开机自启说明

安装开机自启后，每次计算机启动时，系统会自动：
1. 创建 `storage` 和 `logs` 目录（如不存在）
2. 启动监控系统服务
3. 服务在后台运行

您可以通过以下命令查看任务状态：
```cmd
schtasks /Query /TN "MonitorSystem_AutoStart"
```

---

## 故障排查

### 服务无法启动

1. 检查 Python 是否正确安装：`python --version`
2. 检查依赖是否安装：`pip list`
3. 查看启动日志：`logs\startup.log`

### 无法访问网页

1. 确认服务已启动（任务管理器中能看到 python.exe）
2. 检查防火墙是否放行 8888 端口
3. 检查端口是否被其他程序占用：`netstat -ano | findstr 8888`

### 监控设备连接失败

1. 确认目标设备网络可达：`ping <目标IP>`
2. 检查 SSH 账号密码是否正确
3. 确认目标设备 SSH 服务正常运行

---

## 目录结构

```
C:\MonitorSystem\
├── backend\              # 后端代码
│   ├── app\             # 应用代码
│   ├── run_server.py    # 服务入口
│   └── port.txt         # 端口配置
├── frontend\             # 前端页面
├── storage\              # 数据存储（自动创建）
├── logs\                 # 日志目录（自动创建）
├── deploy\               # 部署脚本
│   ├── start.bat        # 启动脚本
│   ├── stop.bat         # 停止脚本
│   ├── install_service.bat    # 安装开机自启
│   └── uninstall_service.bat  # 卸载开机自启
└── requirements.txt     # Python 依赖
```

---

## 技术支持

如遇问题，请检查：
1. Python 版本是否为 3.9+
2. 所有依赖是否安装成功
3. 防火墙是否放行对应端口
