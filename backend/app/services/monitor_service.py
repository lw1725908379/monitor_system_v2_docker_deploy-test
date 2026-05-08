import threading
import time
from backend.app.repositories.device_repository import DeviceRepository
from backend.app.core.ssh_client import SSHClient
from backend.app.core.config import Config
# from backend.app.utils.email_sender import send_email
from backend.app.utils.logger import logger, add_device_context
from backend.shared.database import DatabaseManager


class MonitorService:
    _alert_history = {}
    def __init__(self):
        self.repo = DeviceRepository()

    def check_all_devices_async(self):
        """触发所有设备的异步检查"""
        devices = self.repo.get_all()
        for dev in devices:
            threading.Thread(target=self.check_single_device, args=(dev['ip'],)).start()

    def check_single_device(self, ip):
        """检查单台设备的主逻辑（含风险进程重启检测）"""
        device = self.repo.get_by_ip(ip)
        if not device:
            logger.warning(f"设备不存在: {ip}")
            return

        dev_log = add_device_context(logger, ip)
        dev_log.info(f"开始检查设备...")

        ssh = SSHClient(ip, device['username'], device['password'])

        status = 'offline'
        record = {
            'ip': ip, 'memory': 0, 'cpu': 0,
            'processes': [], 'core_files': [], 'thermal_zones': [], 'status': 'offline'
        }

        try:
            if ssh.connect():
                status = 'online'

                try:
                    base_info, proj_info = ssh.get_device_details()
                    if base_info or proj_info:
                        db = DatabaseManager(Config.DB_PATH)
                        db.add_device_detail(ip, base_info, proj_info)
                        dev_log.info("设备详情已更新")
                except Exception as e:
                    dev_log.error(f"获取设备详情失败: {e}")

                mem_data = ssh.check_memory(Config.MONITOR_CONFIG['memory_threshold'])
                cpu_val = ssh.get_cpu_usage()
                core_files = ssh.check_core_files(Config.MONITOR_CONFIG['core_dump_path'])
                thermal_zones = ssh.get_thermal_zones()

                # ========== 网络监控 ==========
                network_interface = Config.MONITOR_CONFIG.get('network_interface', 'eth0')
                net_data = ssh.get_network_stats(network_interface)

                # 计算流量速率（需要与上次数据对比）
                if net_data:
                    last_net = db.get_latest_network_stats(ip)
                    if last_net:
                        import time
                        try:
                            last_time = time.mktime(time.strptime(str(last_net['check_time']), '%Y-%m-%d %H:%M:%S'))
                            curr_time = time.time()
                            interval = curr_time - last_time
                            if interval > 0:
                                # 计算速率 KB/s
                                net_data['rx_rate'] = (net_data['rx_bytes'] - last_net['rx_bytes']) / 1024 / interval
                                net_data['tx_rate'] = (net_data['tx_bytes'] - last_net['tx_bytes']) / 1024 / interval
                        except:
                            pass

                    # 保存网络数据
                    db.add_network_stats(
                        ip, net_data['interface'], net_data['rx_bytes'], net_data['tx_bytes'],
                        net_data.get('rx_rate', 0), net_data.get('tx_rate', 0),
                        net_data.get('bandwidth_mbps', 100), net_data.get('latency_ms', 0),
                        net_data.get('packet_loss', 0)
                    )

                # ========== 1. 获取所有风险进程（包括手动+自动）先检查PID变化 ==========
                db = DatabaseManager(Config.DB_PATH)
                risk_configs = self.repo.get_custom_risk_processes(ip)
                risk_results = ssh.check_risk_processes(risk_configs)

                risk_alerts = []

                # 记录哪些进程名在运行
                running_processes = set()

                for proc in risk_results:
                    running_processes.add(proc.get('process_name'))

                    db_pid = str(proc.get('pid') or "")
                    new_pid = str(proc.get('fetched_pid') or "")

                    # 检测PID变化（进程重启）
                    is_restart = False
                    if db_pid and new_pid and db_pid != new_pid:
                        msg = f"进程发生重启: {proc['process_name']} (PID: {db_pid} -> {new_pid})"
                        dev_log.warning(msg)
                        restart_alert = proc.copy()
                        restart_alert['alert_msg'] = msg
                        restart_alert['alert_triggered'] = True  # 设置告警状态
                        risk_alerts.append(restart_alert)
                        is_restart = True

                    # 内存超限检测（仅对手动配置的进程）
                    if proc.get('alert_triggered') and proc.get('source') == 'manual' and not is_restart:
                        risk_alerts.append(proc)

                    if new_pid:
                        db.update_custom_risk_process_status(
                            proc['id'],
                            proc.get('current_memory', 0),
                            0,
                            'checked',
                            proc.get('alert_triggered', False),
                            new_pid=new_pid
                        )

                # ========== 2. 保存自动发现的Top进程到数据库 ==========
                top_processes = mem_data.get('high_processes', [])
                for proc in top_processes:
                    if proc.get('pid') and proc.get('command'):
                        # 检查是否已存在（无论是自动还是手动配置）
                        existing = [r for r in risk_configs if r.get('process_name') == proc['command']]
                        if not existing:
                            # 只有不在配置中的进程才自动添加
                            db.add_or_update_auto_process(
                                ip,
                                proc['pid'],
                                proc['command'],
                                proc.get('rss_kb', 0) // 1024,  # 转为MB
                                proc.get('mem_percent', 0)
                            )

                record.update({
                    'memory': mem_data['usage'],
                    'cpu': cpu_val,
                    'processes': mem_data['high_processes'],
                    'core_files': core_files,
                    'thermal_zones': thermal_zones,
                    'network': net_data,
                    'status': 'online'
                })

                self._analyze_alerts(ip, record, risk_alerts)

            else:
                self.repo.add_alert(ip, 'Offline', '设备 SSH 连接失败')

        except Exception as e:
            dev_log.error(f"检查异常: {e}", exc_info=True)
        finally:
            ssh.close()
            self.repo.add_monitoring_record(record)
            dev_log.info(f"检查完成，状态: {status}")

    def _analyze_alerts(self, ip, record, risk_alerts):
        """分析指标，触发邮件告警（含防轰炸机制）"""
        current_time = time.time()

        # 告警类型映射（用于拆分告警）
        alert_categories = {
            'CpuHigh': [],
            'MemoryHigh': [],
            'CoreFile': [],
            'ProcessRestart': [],
            'ProcessOom': [],
            'NetworkTxHigh': [],
            'NetworkPacketLoss': [],
            'NetworkLatency': [],
            'TemperatureHigh': []
        }

        # --- 1. CPU 告警 ---
        if record['cpu'] > Config.MONITOR_CONFIG['cpu_threshold']:
            alert_key = f"{ip}_cpu_high"
            if self._should_send(alert_key):
                alert_categories['CpuHigh'].append(f"CPU 使用率过高: {record['cpu']}%")

        # --- 2. 内存 告警 ---
        if record['memory'] > Config.MONITOR_CONFIG['memory_threshold']:
            alert_key = f"{ip}_memory_high"
            if self._should_send(alert_key):
                alert_categories['MemoryHigh'].append(f"内存 使用率过高: {record['memory']}%")

        # --- 3. Core 文件告警 ---
        if record['core_files']:
            alert_key = f"{ip}_core_found"
            if self._should_send(alert_key):
                filenames = [cf.get('filename', '未知') for cf in record['core_files']]
                if len(filenames) <= 3:
                    files_str = ', '.join(filenames)
                else:
                    files_str = ', '.join(filenames[:3]) + f' 等{len(filenames)}个'
                alert_categories['CoreFile'].append(f"发现新 Core 文件: {files_str}")

        # --- 4. 风险进程告警 ---
        for risk in risk_alerts:
            p_name = risk['process_name']

            # A. 重启告警 (PID 变化)
            if "重启" in risk.get('alert_msg', ''):
                alert_key = f"{ip}_process_restart_{p_name}"
                if self._should_send(alert_key):
                    alert_categories['ProcessRestart'].append(risk['alert_msg'])

            # B. 内存超限告警
            elif risk.get('alert_triggered'):
                alert_key = f"{ip}_process_oom_{p_name}"
                if self._should_send(alert_key):
                    if risk.get('alert_msg'):
                        alert_categories['ProcessOom'].append(risk['alert_msg'])
                    else:
                        alert_categories['ProcessOom'].append(f"风险进程内存超限: {p_name} ({risk['current_memory']}MB)")

        # --- 5. 网络告警 ---
        net = record.get('network')
        if net:
            tx_rate = net.get('tx_rate', 0)
            rx_rate = net.get('rx_rate', 0)
            packet_loss = net.get('packet_loss', 0)
            latency = net.get('latency_ms', 0)

            # 发送速率告警
            if tx_rate > Config.MONITOR_CONFIG.get('tx_rate_threshold', 1024):
                alert_key = f"{ip}_network_tx_high"
                if self._should_send(alert_key):
                    alert_categories['NetworkTxHigh'].append(f"网络发送速率过高: {tx_rate:.1f} KB/s")

            # 丢包率告警
            if packet_loss > Config.MONITOR_CONFIG.get('packet_loss_threshold', 1):
                alert_key = f"{ip}_network_packet_loss"
                if self._should_send(alert_key):
                    alert_categories['NetworkPacketLoss'].append(f"网络丢包率过高: {packet_loss}%")

            # 延迟告警
            if latency > Config.MONITOR_CONFIG.get('latency_threshold', 100):
                alert_key = f"{ip}_network_latency_high"
                if self._should_send(alert_key):
                    alert_categories['NetworkLatency'].append(f"网络延迟过高: {latency} ms")

        # --- 6. 温度告警 ---
        thermal = record.get('thermal_zones', [])
        for t in thermal:
            if t.get('temp', 0) > 80:
                alert_key = f"{ip}_temp_high_{t.get('zone', 'unknown')}"
                if self._should_send(alert_key):
                    alert_categories['TemperatureHigh'].append(f"温度过高: {t.get('zone')} {t.get('temp')}°C")

        # --- 发送拆分后的告警到数据库 ---
        total_alerts = 0
        for alert_type, messages in alert_categories.items():
            if messages:
                # 同一个类型的多个消息合并
                msg = '; '.join(messages)
                self.repo.add_alert(ip, alert_type, msg)
                total_alerts += len(messages)

        if total_alerts > 0:
            logger.info(f"[{ip}] 触发 {total_alerts} 个告警")

    def _should_send(self, key, cooldown=None):
        """
        检查是否应该发送告警 (冷却机制)
        :param key: 告警唯一标识 (IP + 类型)
        :param cooldown: 自定义冷却时间(秒)，默认使用全局配置
        """
        if cooldown is None:
            cooldown = getattr(Config, 'ALERT_COOLDOWN', 3600)  # 默认1小时

        last_time = self._alert_history.get(key, 0)
        now = time.time()

        if now - last_time > cooldown:
            # 超过冷却时间，允许发送，并更新时间
            self._alert_history[key] = now
            return True
        else:
            # 在冷却期内，拦截（不打印日志）
            # logger.debug(f"告警被拦截(冷却中): {key}")
            return False