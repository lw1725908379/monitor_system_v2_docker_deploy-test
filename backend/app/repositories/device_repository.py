from backend.shared.database import DatabaseManager
from backend.app.core.config import Config


class DeviceRepository:
    def __init__(self):
        self.db = DatabaseManager(Config.DB_PATH)

    def get_all(self):
        return self.db.get_all_devices()

    def get_by_ip(self, ip):
        devices = self.db.get_all_devices()
        for d in devices:
            if d['ip'] == ip:
                return d
        return None

    def add_monitoring_record(self, data):
        return self.db.add_monitoring_record(
            data['ip'],
            data['memory'],
            data['cpu'],
            data['processes'],
            data['core_files'],
            data.get('thermal_zones', []),
            data['status']
        )

    def get_latest_record(self, ip):
        return self.db.get_latest_monitoring_record(ip)

    def get_latest_records_batch(self, ips):
        """批量获取多个设备的最新记录（优化版）"""
        return self.db.get_latest_monitoring_records_batch(ips)

    def add_alert(self, ip, type, msg):
        return self.db.add_alert(ip, type, msg)

    def get_custom_risk_processes(self, ip):
        return self.db.get_custom_risk_processes(ip)

    def add_device(self, ip, product_line, user, pwd):
        return self.db.add_device(ip, product_line, user, pwd)

    def device_exists(self, ip):
        return self.db.device_exists(ip)

    def delete_device(self, ip):
        return self.db.delete_device(ip)

    def batch_delete_devices(self, ips):
        return self.db.batch_delete_devices(ips)

    def update_device(self, ip, product_line=None, username=None, password=None):
        return self.db.update_device(ip, product_line, username, password)

    def batch_update_product_line(self, ips, product_line):
        return self.db.batch_update_product_line(ips, product_line)

    def add_risk_process_config(self, ip, pid, name, memory_limit):
        return self.db.add_custom_risk_process(ip, pid, name, memory_limit, source='manual')

    def delete_risk_process_config(self, id):
        return self.db.delete_custom_risk_process(id)

    def get_offline_devices(self, days=3):
        return self.db.get_offline_devices(days)

    def delete_device_keep_history(self, ip):
        return self.db.delete_device_keep_history(ip)