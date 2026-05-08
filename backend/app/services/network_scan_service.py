import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from backend.app.core.ssh_client import SSHClient
from backend.app.utils.logger import logger


class NetworkScanService:
    """局域网设备扫描服务 - 优化版"""

    def __init__(self):
        self.jieshun_credentials = {'username': 'root', 'password': 'Jsst_168'}
        self.scan_timeout = 2  # TCP连接超时(秒)
        self.ssh_timeout = 3   # SSH连接超时(秒)
        self.ping_workers = 30  # TCP扫描并发数
        self.ssh_workers = 10   # SSH验证并发数

        # 设备缓存 {ip: {'last_seen': timestamp, 'is_jieshun': bool}}
        self._device_cache = {}
        self._cache_ttl = 300    # 缓存有效期5分钟
        self._cache_lock = threading.Lock()

    def _is_cached(self, ip):
        """检查缓存"""
        with self._cache_lock:
            if ip in self._device_cache:
                cached = self._device_cache[ip]
                if time.time() - cached['last_seen'] < self._cache_ttl:
                    return cached
        return None

    def _update_cache(self, ip, is_jieshun):
        """更新缓存"""
        with self._cache_lock:
            self._device_cache[ip] = {
                'last_seen': time.time(),
                'is_jieshun': is_jieshun
            }

    def _ping_host(self, ip):
        """检测主机是否在线 - 直接尝试SSH连接（更可靠）"""
        try:
            # 直接尝试SSH连接来检测设备，比TCP端口检测更可靠
            client = SSHClient(
                ip,
                self.jieshun_credentials['username'],
                self.jieshun_credentials['password']
            )
            if client.connect():
                client.close()
                return True
            client.close()
        except Exception:
            pass
        return False

    def _check_ssh_device(self, ip):
        """检查 SSH 设备是否是捷顺产品"""
        try:
            client = SSHClient(
                ip,
                self.jieshun_credentials['username'],
                self.jieshun_credentials['password']
            )
            if client.connect():
                # 尝试执行命令验证是捷顺设备
                result = client.execute_cmd('cat /opt/jsst/config/JSM1689/baseinfo.json 2>/dev/null')
                client.close()
                if result and ('cpuId' in result or 'devId' in result or 'deviceId' in result):
                    return True
            else:
                client.close()
        except Exception as e:
            logger.debug(f"[{ip}] SSH 连接验证失败: {e}")
        return False

    def _fast_ping_scan(self, ip_list, callback=None):
        """
        阶段1：快速Ping扫描，发现在线主机
        使用高并发，发现所有在线IP
        """
        online_ips = []
        lock = threading.Lock()

        def ping_single(ip):
            # 先检查缓存
            cached = self._is_cached(ip)
            if cached and cached['is_jieshun']:
                with lock:
                    online_ips.append(ip)
                    logger.debug(f"[缓存命中] {ip}")
                if callback:
                    callback(ip, True, cached['is_jieshun'])
                return ip

            if self._ping_host(ip):
                with lock:
                    online_ips.append(ip)
                if callback:
                    callback(ip, True, cached['is_jieshun'] if cached else False)
            elif callback:
                callback(ip, False, False)
            return ip

        with ThreadPoolExecutor(max_workers=self.ping_workers) as executor:
            futures = {executor.submit(ping_single, ip): ip for ip in ip_list}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Ping扫描异常: {e}")

        return online_ips

    def _verify_ssh_devices(self, online_ips, callback=None):
        """
        阶段2：SSH验证捷顺设备
        使用较低并发，避免对目标主机造成压力
        """
        jieshun_devices = []
        lock = threading.Lock()

        def verify_single(ip):
            # 检查缓存
            cached = self._is_cached(ip)
            if cached and cached['is_jieshun']:
                result = {'ip': ip, 'online': True, 'is_jieshun': True}
                with lock:
                    jieshun_devices.append(result)
                logger.debug(f"[缓存命中] {ip} 是捷顺设备")
                if callback:
                    callback(ip, True, True)
                return result

            # SSH验证
            is_jieshun = self._check_ssh_device(ip)
            self._update_cache(ip, is_jieshun)

            result = {'ip': ip, 'online': True, 'is_jieshun': is_jieshun}
            if is_jieshun:
                with lock:
                    jieshun_devices.append(result)
                    logger.info(f"[扫描] 发现捷顺设备: {ip}")
            if callback:
                callback(ip, True, is_jieshun)
            return result

        with ThreadPoolExecutor(max_workers=self.ssh_workers) as executor:
            futures = {executor.submit(verify_single, ip): ip for ip in online_ips}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"SSH验证异常: {e}")

        return jieshun_devices

    def scan_network(self, subnet, start_ip, end_ip, callback=None):
        """
        扫描局域网设备 - 直接SSH验证（更可靠）

        直接通过SSH连接验证捷顺设备，比TCP端口检测更准确

        Args:
            subnet: 网段前缀，如 192.168.1
            start_ip: 起始 IP 尾数，如 1
            end_ip: 结束 IP 尾数，如 254
            callback: 进度回调函数 callback(ip, online, is_jieshun)

        Returns:
            list: 发现的捷顺设备列表
        """
        logger.info(f"[扫描开始] {subnet}.{start_ip}-{end_ip}")

        # 生成IP列表
        ip_list = [f"{subnet}.{i}" for i in range(int(start_ip), int(end_ip) + 1)]
        total = len(ip_list)
        jieshun_devices = []
        checked = 0
        lock = threading.Lock()

        def scan_single(ip):
            nonlocal checked

            # 检查缓存
            cached = self._is_cached(ip)
            if cached and cached['is_jieshun']:
                with lock:
                    jieshun_devices.append({'ip': ip, 'online': True, 'is_jieshun': True})
                with lock:
                    checked += 1
                if callback:
                    callback(ip, True, True)
                return

            # 直接SSH验证捷顺设备
            is_jieshun = self._check_ssh_device(ip)
            self._update_cache(ip, is_jieshun)

            if is_jieshun:
                with lock:
                    jieshun_devices.append({'ip': ip, 'online': True, 'is_jieshun': True})
                    logger.info(f"[扫描] 发现捷顺设备: {ip}")

            with lock:
                checked += 1
            if callback:
                callback(ip, is_jieshun, is_jieshun)

        # 直接使用SSH验证（并发数降低，避免对目标主机压力过大）
        logger.info(f"[扫描] 开始SSH验证，共{total}个IP...")
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = {executor.submit(scan_single, ip): ip for ip in ip_list}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"扫描异常: {e}")

        logger.info(f"[扫描] 完成，发现{len(jieshun_devices)}台捷顺设备")
        return jieshun_devices
