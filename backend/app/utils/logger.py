import logging
import logging.handlers
import os
import sys
from typing import Optional

class DeviceFormatter(logging.Formatter):
    """设备监控专用日志格式器"""
    default_time_format = "%Y-%m-%d %H:%M:%S"

    def format(self, record):
        device_ip = getattr(record, "device_ip", None)
        module_name = getattr(record, "module_name", None)

        parts = [
            self.formatTime(record, self.default_time_format),
            record.levelname
        ]
        if module_name:
            parts.append(f"[{module_name}]")
        if device_ip:
            parts.append(f"[{device_ip}]")

        parts.append(record.getMessage())

        if record.exc_info:
            parts.append(self.formatException(record.exc_info))

        return " | ".join(parts)

def setup_logger(
    name: str = "monitor",
    module_name: Optional[str] = None,
    debug: bool = True
) -> logging.Logger:
    """
    创建模块专用日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    if not logger.handlers:
        formatter = DeviceFormatter()

        # 1. 控制台输出
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 2. 文件输出 (自动计算 logs 目录)
        # 容器内用 /app/logs，开发用相对路径
        if os.path.exists('/app'):
            base_dir = '/app'
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, "monitor_system.log")

        file_handler = logging.handlers.RotatingFileHandler(
            log_file_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    if module_name:
        return logging.LoggerAdapter(logger, {"module_name": module_name})

    return logger

def add_device_context(logger: logging.Logger, device_ip: str) -> logging.LoggerAdapter:
    """返回带设备 IP 的 LoggerAdapter"""
    return logging.LoggerAdapter(logger, {"device_ip": device_ip})

logger = setup_logger()