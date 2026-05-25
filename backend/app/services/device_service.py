from backend.app.repositories.device_repository import DeviceRepository
from backend.app.core.config import Config
from backend.app.utils.logger import logger
import time
import threading

class DeviceService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.repo = DeviceRepository()
        # 后端缓存
        self._cache = {}
        self._cache_ttl = 5  # 缓存5秒
        self._cache_timestamp = 0
        self._cache_hits = 0  # 缓存命中次数
        self._cache_misses = 0  # 缓存未命中次数
        self._initialized = True

    def get_all_devices_with_status(self):
        """获取所有设备状态（使用批量查询优化 + 缓存）"""
        current_time = time.time()

        # 检查缓存是否有效
        if self._cache and (current_time - self._cache_timestamp) < self._cache_ttl:
            self._cache_hits += 1
            return self._cache

        self._cache_misses += 1

        # 批量查询：1次获取所有设备 + 1次获取所有最新记录 = 2次查询
        devices = self.repo.get_all()
        if not devices:
            self._cache = []
            self._cache_timestamp = current_time
            return []

        ips = [d['ip'] for d in devices]
        latest_records = self.repo.get_latest_records_batch(ips)

        result = []
        for d in devices:
            latest = latest_records.get(d['ip'])
            d['latest_record'] = latest
            d['status'] = latest.get('status', 'offline') if latest else 'unknown'
            d['last_check'] = latest.get('check_time') if latest else 'N/A'
            result.append(d)

        # 更新缓存
        self._cache = result
        self._cache_timestamp = current_time
        return result

    def invalidate_cache(self):
        """手动失效缓存（用于设备增删改后）"""
        self._cache = {}
        self._cache_timestamp = 0

    def get_cache_stats(self):
        """获取缓存统计信息"""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
        return {
            'hits': self._cache_hits,
            'misses': self._cache_misses,
            'hit_rate': round(hit_rate, 2)
        }

    def add_device(self, data):
        ip = data['ip']
        # 检查设备是否已存在
        if self.repo.device_exists(ip):
            return False
        result = self.repo.add_device(
            ip,
            data.get('product_line', '未分类'),
            data.get('username', 'root'),
            data.get('password', 'Jsst_168')
        )
        # 失效缓存
        self.invalidate_cache()
        return result

    def delete_device(self, ip):
        result = self.repo.delete_device(ip)
        # 失效缓存
        self.invalidate_cache()
        return result

    def cleanup_offline_devices(self):
        """清理离线超过指定天数的设备（保留监控历史数据）"""
        if not Config.DEVICE_CLEANUP_CONFIG.get('enabled', True):
            logger.info("设备自动清理已禁用")
            return {'deleted_count': 0, 'deleted_ips': []}

        days = Config.DEVICE_CLEANUP_CONFIG.get('offline_days_threshold', 3)
        logger.info(f"开始清理离线超过 {days} 天的设备...")

        # 获取离线设备列表
        offline_devices = self.repo.get_offline_devices(days)

        if not offline_devices:
            logger.info("没有需要清理的离线设备")
            return {'deleted_count': 0, 'deleted_ips': []}

        deleted_ips = []
        for device in offline_devices:
            ip = device['ip']
            last_check = device.get('last_check_time', '未知')
            logger.info(f"清理离线设备: {ip} (最后检查: {last_check})")
            self.repo.delete_device_keep_history(ip)
            deleted_ips.append(ip)

        count = len(deleted_ips)
        logger.info(f"离线设备清理完成，共清理 {count} 台设备: {deleted_ips}")

        # 失效缓存
        self.invalidate_cache()

        return {'deleted_count': count, 'deleted_ips': deleted_ips}