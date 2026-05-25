import os


class Config:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # 存储目录
    STORAGE_DIR = os.path.join(os.path.dirname(BASE_DIR), "storage")

    # 数据库路径
    DB_PATH = os.path.join(STORAGE_DIR, "devices.db")

    REPORT_DIR = os.path.join(STORAGE_DIR, "reports")

    # ================= 2. 业务阈值配置 =================
    MONITOR_CONFIG = {
        'memory_threshold': 95,  # 内存总报警阈值 (%)
        'cpu_threshold': 95,  # CPU报警阈值 (%)
        'check_interval': 30,  # 检查间隔 (秒)
        'core_dump_path': '/opt/jsst/coredump/',
        'auto_process_threshold': 30.0, # 默认风险进程内存超出阈值（%）
        'top_process_count': 5,
        'process_mem_min_pct': 1.0,  # 仅记录占用 > 1% 的进程
        # 网络监控配置
        'network_interface': 'eth0',  # 默认网卡
        'tx_rate_threshold': 1024,   # 发送速率告警阈值 KB/s (默认1MB/s)
        'rx_rate_threshold': 5120,    # 接收速率告警阈值 KB/s (默认5MB/s)
        'packet_loss_threshold': 1,   # 丢包率告警阈值 (%)
        'latency_threshold': 100,     # 延迟告警阈值 (ms)
    }

    # ================= 3. SSH 连接配置 =================
    SSH_CONFIG = {
        'connect_timeout': 10,  # 连接超时
        'exec_timeout': 30,  # 命令执行超时
    }

    # ================= 4. Linux 命令集 =================
    LINUX_COMMANDS = {
        # 基础信息
        'BASEINFO_CMD': 'cat /opt/jsst/config/JSM1689/baseinfo.json',
        'PROJECT_CMD': 'cat /opt/jsst/config/nms/project_info.json',

        # 资源监控
        'CPU_STAT': "cat /proc/stat | grep '^cpu '",
        'MEM_FREE': "free | grep Mem | awk '{print $2, $3}'",
        'TOP_PROCESSES': "ps -eo pid,user,comm,rss --sort=-rss | head -n {count}",

        # 风险进程检测 (BusyBox 适配)
        'PIDOF': "pidof {process_name}",
        'PS_GREP': "ps | grep '{process_name}' | grep -v grep | awk '{{print $1}}'",
        'PROC_STATUS_VMRSS': "cat /proc/{pid}/status | grep VmRSS",

        # Core 文件
        'FIND_CORE_FILES': 'ls {path} 2>/dev/null',

        # 热区温度
        'THERMAL_ZONES': "for zone in /sys/class/thermal/thermal_zone*; do if [ -d \"$zone\" ]; then type=$(cat \"$zone/type\" 2>/dev/null); temp=$(cat \"$zone/temp\" 2>/dev/null); if [ -n \"$temp\" ]; then temp_c=$(awk \"BEGIN {printf \\\"%.2f\\\", $temp / 1000}\"); echo \"$type:$temp_c\"; fi; fi; done"
    }

    # ================= 5. 邮件配置 =================
    EMAIL_CONFIG = {
        'smtp_server': 'smtp.qq.com',
        'smtp_port': 587,
        'sender': '1725908379@qq.com',
        'password': 'udvdnuobigcdhhjd',
        'receivers': ['1725908379@qq.com'],
        'subject_prefix': '[设备监控告警]'
    }

    ALERT_COOLDOWN = 24 * 60 * 60 # 告警冷却时间 (秒)

    # 设备清理配置
    DEVICE_CLEANUP_CONFIG = {
        'offline_days_threshold': 3,  # 离线超过3天自动清理
        'enabled': True,              # 是否启用自动清理
    }

    # ================= 6. ML模型配置 =================
    ML_MODEL_CONFIG = {
        'ridge_alpha': 1.0,           # Ridge回归正则化参数
        'analysis_days': 7,           # 分析历史天数
        'prediction_steps': 120,     # 预测步数（1小时=120步×30秒）
        'min_data_points': 50,       # 最少数据点数量
        'safety_margin': {           # 安全边际(%)
            'stable': 5,              # 稳定趋势
            'up': 10,                 # 上升趋势
            'leak': 15,               # 泄漏趋势
        },
        'trend_threshold': {          # 趋势判断阈值(MB/小时)
            'leak': 1.0,              # 超过此值疑似泄漏
            'down': -1.0,             # 低于此值疑似下降
        }
    }


if not os.path.exists(Config.STORAGE_DIR):
    os.makedirs(Config.STORAGE_DIR, exist_ok=True)

if not os.path.exists(Config.REPORT_DIR):
    os.makedirs(Config.REPORT_DIR, exist_ok=True)