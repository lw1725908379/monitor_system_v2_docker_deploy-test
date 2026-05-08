import json
import time
import logging
from datetime import datetime
from backend.shared.database import DatabaseManager
from backend.app.core.config import Config
from backend.app.core.ssh_client import SSHClient

logger = logging.getLogger(__name__)


class TemperatureTestService:
    def __init__(self):
        self.db = DatabaseManager(Config.DB_PATH)

    def start_test(self, device_ip, test_phase, test_duration, threshold_memory_pct, threshold_temp_pct, baseline_id=None):
        """启动温度测试"""
        # 验证设备存在
        devices = self.db.get_all_devices()
        device = None
        for d in devices:
            if d['ip'] == device_ip:
                device = d
                break

        if not device:
            raise ValueError(f"设备 {device_ip} 不存在")

        # 创建测试记录
        test_id = self.db.create_temperature_test(
            device_ip, test_phase, test_duration,
            threshold_memory_pct, threshold_temp_pct, baseline_id
        )

        # 如果是高温/低温测试，需要验证baseline_id存在
        if test_phase in ['high', 'low'] and baseline_id:
            baseline = self.db.get_temperature_test(baseline_id)
            if not baseline or baseline['test_phase'] != 'baseline':
                raise ValueError("基准测试不存在或不是常温基准")

        logger.info(f"启动温度测试: test_id={test_id}, device={device_ip}, phase={test_phase}")
        return test_id

    def stop_test(self, test_id):
        """停止温度测试"""
        self.db.stop_temperature_test(test_id)
        logger.info(f"停止温度测试: test_id={test_id}")

    def get_test(self, test_id):
        """获取测试详情"""
        test = self.db.get_temperature_test(test_id)
        if test:
            # 获取测试数据
            test['data'] = self.db.get_temperature_test_data(test_id)
            # 如果有基准，获取基准数据
            if test['baseline_id']:
                baseline = self.db.get_temperature_test(test['baseline_id'])
                if baseline:
                    baseline['data'] = self.db.get_temperature_test_data(baseline['id'])
                    test['baseline'] = baseline
        return test

    def get_tests(self, device_ip=None, status=None):
        """获取测试列表"""
        return self.db.get_temperature_tests(device_ip, status)

    def get_baseline_tests(self, device_ip):
        """获取常温基准测试列表"""
        return self.db.get_baseline_tests(device_ip)

    def delete_test(self, test_id):
        """删除温度测试记录"""
        self.db.delete_temperature_test(test_id)
        logger.info(f"删除温度测试: test_id={test_id}")

    def collect_test_data(self, test_id):
        """采集测试数据（被调度器调用）"""
        test = self.db.get_temperature_test(test_id)
        if not test or test['status'] != 'running':
            return

        device_ip = test['device_ip']
        baseline_id = test['baseline_id']

        # 获取设备信息
        devices = self.db.get_all_devices()
        device = None
        for d in devices:
            if d['ip'] == device_ip:
                device = d
                break

        if not device:
            logger.error(f"设备 {device_ip} 不存在")
            return

        # SSH连接
        ssh = SSHClient(device_ip, device['username'], device['password'])
        if not ssh.connect():
            logger.error(f"无法连接到设备 {device_ip}")
            return

        try:
            # 采集数据
            mem_data = ssh.check_memory(Config.MONITOR_CONFIG['memory_threshold'])
            thermal_zones = ssh.get_thermal_zones()
            core_files = ssh.check_core_files(Config.MONITOR_CONFIG['core_dump_path'])

            # 获取进程数据
            from backend.app.repositories.device_repository import DeviceRepository
            repo = DeviceRepository()
            risk_configs = repo.get_custom_risk_processes(device_ip)
            process_results = ssh.check_risk_processes(risk_configs)

            # 处理进程数据
            process_data = []
            for proc in process_results:
                process_data.append({
                    'name': proc.get('process_name'),
                    'pid': proc.get('fetched_pid'),
                    'memory': proc.get('current_memory', 0)
                })

            # 计算与基准的偏差
            memory_delta_pct = 0
            thermal_delta_pct = 0
            exceptions = []

            if baseline_id:
                baseline_data = self.db.get_temperature_test_data(baseline_id)
                if baseline_data:
                    # 计算内存偏差
                    baseline_memory = baseline_data[-1]['memory_usage'] if baseline_data else 0
                    if baseline_memory > 0:
                        memory_delta_pct = ((mem_data['usage'] - baseline_memory) / baseline_memory) * 100

                    # 计算温度偏差
                    baseline_thermal = baseline_data[-1]['thermal_zones'] if baseline_data else []
                    if baseline_thermal:
                        baseline_avg_temp = sum(t['temp'] for t in baseline_thermal) / len(baseline_thermal)
                        current_avg_temp = sum(t['temp'] for t in thermal_zones) / len(thermal_zones) if thermal_zones else 0
                        if baseline_avg_temp > 0:
                            thermal_delta_pct = ((current_avg_temp - baseline_avg_temp) / baseline_avg_temp) * 100

            # 检测异常：进程重启
            process_restarts = []
            if baseline_id:
                baseline_data = self.db.get_temperature_test_data(baseline_id)
                if baseline_data:
                    baseline_processes = {p['name']: p['pid'] for p in baseline_data[-1]['process_data']}
                    for proc in process_data:
                        if proc['name'] in baseline_processes:
                            if baseline_processes[proc['name']] != proc['pid']:
                                process_restarts.append({
                                    'name': proc['name'],
                                    'old_pid': baseline_processes[proc['name']],
                                    'new_pid': proc['pid']
                                })
                                exceptions.append({
                                    'type': 'process_restart',
                                    'message': f"进程 {proc['name']} 发生重启 (PID: {baseline_processes[proc['name']]} -> {proc['pid']})"
                                })

            # 检测异常：内存偏差超过阈值
            if test['threshold_memory_pct'] and abs(memory_delta_pct) > test['threshold_memory_pct']:
                exceptions.append({
                    'type': 'memory_threshold',
                    'message': f"内存偏差 {memory_delta_pct:.1f}% 超过阈值 {test['threshold_memory_pct']}%"
                })

            # 检测异常：温度偏差超过阈值
            if test['threshold_temp_pct'] and abs(thermal_delta_pct) > test['threshold_temp_pct']:
                exceptions.append({
                    'type': 'thermal_threshold',
                    'message': f"温度偏差 {thermal_delta_pct:.1f}% 超过阈值 {test['threshold_temp_pct']}%"
                })

            # 保存数据
            self.db.add_temperature_test_data(
                test_id, process_data, mem_data['usage'], memory_delta_pct,
                thermal_zones, thermal_delta_pct, process_restarts, core_files, exceptions
            )

            # 检查测试是否超时
            if test['test_duration']:
                start_time = datetime.strptime(test['start_time'], '%Y-%m-%d %H:%M:%S')
                elapsed_minutes = (datetime.now() - start_time).total_seconds() / 60
                if elapsed_minutes >= test['test_duration']:
                    self.db.complete_temperature_test(test_id)
                    logger.info(f"温度测试完成: test_id={test_id}")

        except Exception as e:
            logger.error(f"采集温度测试数据失败: {e}", exc_info=True)
        finally:
            ssh.close()

    def collect_all_running_tests(self):
        """采集所有正在进行的测试数据"""
        running_tests = self.db.get_running_temperature_tests()
        for test in running_tests:
            try:
                self.collect_test_data(test['id'])
            except Exception as e:
                logger.error(f"采集测试 {test['id']} 数据失败: {e}")
