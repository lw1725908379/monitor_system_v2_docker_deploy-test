import sqlite3
import json
import os
import logging
import time
from typing import List, Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("database")


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        self.init_database()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        return conn

    def execute_command(self, query: str, params: tuple = (), retry=3) -> bool:
        """执行SQL命令，支持重试"""
        for attempt in range(retry):
            conn = self._get_connection()
            try:
                conn.execute(query, params)
                conn.commit()
                return True
            except Exception as e:
                if "locked" in str(e).lower() and attempt < retry - 1:
                    logger.warning(f"数据库锁定，{attempt + 1}/{retry}次重试...")
                    time.sleep(0.5 * (attempt + 1))  # 递增延迟
                    continue
                logger.error(f"SQL执行失败: {query}, 错误: {e}")
                return False
            finally:
                conn.close()

    def execute_query(self, query: str, params: tuple = ()) -> List[Any]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"查询失败: {query}, 错误: {e}")
            return []
        finally:
            conn.close()

    def init_database(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # 1. 设备表 (device_type -> product_line)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip TEXT UNIQUE NOT NULL,
                    product_line TEXT NOT NULL,
                    username TEXT,
                    password TEXT,
                    created_time TIMESTAMP DEFAULT (datetime('now', 'localtime'))
                )
            ''')

            # 2. 设备详情表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS device_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_ip TEXT UNIQUE NOT NULL,
                    cpu_id TEXT,
                    dev_id TEXT,
                    device_id INTEGER,
                    inner_net_card TEXT,
                    mac TEXT,
                    mg_id TEXT,
                    out_net_card TEXT,
                    start_times INTEGER,
                    project_number TEXT,
                    last_updated TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY (device_ip) REFERENCES devices (ip)
                )
            ''')

            # 3. 风险进程配置表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS custom_risk_processes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_ip TEXT NOT NULL,
                    pid TEXT,
                    process_name TEXT NOT NULL,
                    allocated_memory INTEGER NOT NULL,
                    current_memory INTEGER DEFAULT 0,
                    memory_usage_percent REAL DEFAULT 0,
                    status TEXT DEFAULT 'checking',
                    alert_triggered BOOLEAN DEFAULT 0,
                    last_check_time TIMESTAMP,
                    created_time TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    source TEXT DEFAULT 'manual',
                    FOREIGN KEY (device_ip) REFERENCES devices (ip)
                )
            ''')
            # 添加 source 字段（如果不存在）
            try:
                cursor.execute("ALTER TABLE custom_risk_processes ADD COLUMN source TEXT DEFAULT 'manual'")
            except:
                pass

            # 4. 风险进程历史记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS risk_process_monitoring_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_ip TEXT NOT NULL,
                    pid TEXT,
                    process_name TEXT NOT NULL,
                    allocated_memory INTEGER NOT NULL,
                    current_memory INTEGER NOT NULL,
                    memory_usage_percent REAL NOT NULL,
                    check_time TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    alert_triggered BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (device_ip) REFERENCES devices (ip)
                )
            ''')

            # 5. 监控历史表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS monitoring_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_ip TEXT NOT NULL,
                    check_time TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    memory_usage REAL,
                    cpu_usage REAL,
                    high_memory_processes TEXT,
                    new_core_files TEXT,
                    thermal_zones TEXT,
                    status TEXT,
                    FOREIGN KEY (device_ip) REFERENCES devices (ip)
                )
            ''')

            # 6. 告警表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_ip TEXT NOT NULL,
                    alert_time TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    alert_type TEXT NOT NULL,
                    alert_message TEXT NOT NULL,
                    resolved BOOLEAN DEFAULT 0,
                    FOREIGN KEY (device_ip) REFERENCES devices (ip)
                )
            ''')

            # 7. Core文件记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS core_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_ip TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    filesize INTEGER,
                    created_time TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    UNIQUE (device_ip, filename, timestamp),
                    FOREIGN KEY (device_ip) REFERENCES devices (ip)
                )
            ''')

            # 8. 温度测试记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS temperature_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_ip TEXT NOT NULL,
                    test_phase TEXT NOT NULL,
                    test_duration INTEGER,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    status TEXT DEFAULT 'running',
                    threshold_memory_pct REAL,
                    threshold_temp_pct REAL,
                    baseline_id INTEGER,
                    created_time TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    FOREIGN KEY (device_ip) REFERENCES devices (ip),
                    FOREIGN KEY (baseline_id) REFERENCES temperature_tests (id)
                )
            ''')

            # 9. 温度测试数据记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS temperature_test_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id INTEGER NOT NULL,
                    check_time TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    process_data TEXT,
                    memory_usage REAL,
                    memory_delta_pct REAL,
                    thermal_zones TEXT,
                    thermal_delta_pct REAL,
                    process_restarts TEXT,
                    core_files TEXT,
                    exceptions TEXT,
                    FOREIGN KEY (test_id) REFERENCES temperature_tests (id)
                )
            ''')

            # 10. 内存分析记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memory_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_ip TEXT NOT NULL,
                    process_name TEXT NOT NULL,
                    analysis_date DATE NOT NULL,
                    -- 统计特征
                    max_memory REAL,
                    avg_memory REAL,
                    p95_memory REAL,
                    std_memory REAL,
                    data_points INTEGER,
                    -- 趋势分析
                    growth_rate REAL,  -- MB/小时
                    trend_status TEXT,  -- 'leak'(泄漏) / 'down'(下降) / 'stable'(稳定)
                    -- 推荐值
                    recommended_memory INTEGER,
                    -- 告警
                    alert_message TEXT,
                    created_time TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    UNIQUE(device_ip, process_name, analysis_date)
                )
            ''')

            # 11. 内存分析任务日志表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memory_analysis_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    status TEXT,  -- 'running' / 'completed' / 'failed'
                    summary TEXT,
                    alerts TEXT,
                    created_time TIMESTAMP DEFAULT (datetime('now', 'localtime'))
                )
            ''')

            # 12. 网络监控历史表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS network_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_ip TEXT NOT NULL,
                    check_time TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    interface TEXT,
                    rx_bytes BIGINT,
                    tx_bytes BIGINT,
                    rx_rate REAL,
                    tx_rate REAL,
                    bandwidth_mbps REAL,
                    latency_ms REAL,
                    packet_loss REAL
                )
            ''')

            # 13. 模型评估记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS model_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_ip TEXT NOT NULL,
                    process_name TEXT NOT NULL,
                    evaluation_date TEXT NOT NULL,
                    data_points INTEGER NOT NULL,
                    train_size INTEGER NOT NULL,
                    test_size INTEGER NOT NULL,
                    r2_score REAL,
                    mae REAL,
                    rmse REAL,
                    mape REAL,
                    max_ae REAL,
                    predicted_trend TEXT,
                    actual_trend TEXT,
                    trend_correct BOOLEAN,
                    recommended_memory INTEGER,
                    predicted_max REAL,
                    actual_max REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(device_ip, process_name, evaluation_date)
                )
            ''')

            # 14. 预测误差记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prediction_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_ip TEXT NOT NULL,
                    process_name TEXT NOT NULL,
                    prediction_date TEXT NOT NULL,
                    check_date TEXT NOT NULL,
                    predicted_value REAL NOT NULL,
                    actual_value REAL NOT NULL,
                    error_pct REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.commit()
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
        finally:
            conn.close()

    # =======================================================
    # 业务方法：设备管理
    # =======================================================

    def get_all_devices(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self.execute_query("SELECT * FROM devices ORDER BY created_time DESC")]

    def add_device(self, ip, product_line, username, password):
        return self.execute_command(
            "INSERT INTO devices (ip, product_line, username, password) VALUES (?, ?, ?, ?)",
            (ip, product_line, username, password)
        )

    def delete_device(self, ip):
        return self.execute_command("DELETE FROM devices WHERE ip = ?", (ip,))

    def batch_delete_devices(self, ips):
        """批量删除设备"""
        if not ips:
            return 0
        placeholders = ','.join('?' * len(ips))
        self.execute_command(f"DELETE FROM devices WHERE ip IN ({placeholders})", ips)
        return len(ips)

    def get_offline_devices(self, days=3):
        """获取离线超过指定天数的设备"""
        rows = self.execute_query("""
            SELECT d.ip, d.product_line, m.check_time as last_check_time, m.status
            FROM devices d
            LEFT JOIN (
                SELECT device_ip, MAX(check_time) as check_time, status
                FROM monitoring_history
                GROUP BY device_ip
            ) m ON d.ip = m.device_ip
            WHERE m.status = 'offline'
              AND m.check_time < datetime('now', ?, 'localtime')
        """, (f"-{days} days",))
        return [
            {'ip': row[0], 'product_line': row[1], 'last_check_time': row[2], 'status': row[3]}
            for row in rows
        ]

    def delete_device_keep_history(self, ip):
        """删除设备但保留监控历史数据（只删除设备主记录）"""
        # 删除设备详情
        self.execute_command("DELETE FROM device_details WHERE device_ip = ?", (ip,))
        # 删除风险进程配置
        self.execute_command("DELETE FROM custom_risk_processes WHERE device_ip = ?", (ip,))
        # 删除网络统计
        self.execute_command("DELETE FROM network_stats WHERE device_ip = ?", (ip,))
        # 最后删除设备主记录
        self.execute_command("DELETE FROM devices WHERE ip = ?", (ip,))
        return True

    def update_device(self, ip, product_line=None, username=None, password=None):
        """更新设备信息"""
        updates = []
        params = []
        if product_line is not None:
            updates.append("product_line = ?")
            params.append(product_line)
        if username is not None:
            updates.append("username = ?")
            params.append(username)
        if password is not None:
            updates.append("password = ?")
            params.append(password)

        if not updates:
            return False

        params.append(ip)
        query = f"UPDATE devices SET {', '.join(updates)} WHERE ip = ?"
        return self.execute_command(query, tuple(params))

    def batch_update_product_line(self, ips, product_line):
        """批量更新设备产品线"""
        if not ips:
            return False
        placeholders = ','.join(['?'] * len(ips))
        query = f"UPDATE devices SET product_line = ? WHERE ip IN ({placeholders})"
        return self.execute_command(query, (product_line, *ips))

    def device_exists(self, ip):
        rows = self.execute_query("SELECT 1 FROM devices WHERE ip = ?", (ip,))
        return len(rows) > 0

    def get_device_detail(self, device_ip):
        rows = self.execute_query('SELECT * FROM device_details WHERE device_ip = ?', (device_ip,))
        return dict(rows[0]) if rows else {}

    def add_device_detail(self, device_ip, baseinfo, project_info):
        return self.execute_command('''
            INSERT OR REPLACE INTO device_details 
            (device_ip, cpu_id, dev_id, device_id, inner_net_card, mac, mg_id, out_net_card, start_times, project_number, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        ''', (
            device_ip,
            baseinfo.get('cpuId'), baseinfo.get('devId'), baseinfo.get('deviceId'),
            baseinfo.get('innerNetCard'), baseinfo.get('mac'), baseinfo.get('mgId'),
            baseinfo.get('outNetCard'), baseinfo.get('startTimes'),
            project_info.get('project_number')
        ))

    # =======================================================
    # 业务方法：监控与统计
    # =======================================================

    def add_monitoring_record(self, device_ip, memory, cpu, processes, core_files, thermal_zones, status):
        return self.execute_command('''
            INSERT INTO monitoring_history (device_ip, memory_usage, cpu_usage, high_memory_processes, new_core_files, thermal_zones, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (device_ip, memory, cpu, json.dumps(processes), json.dumps(core_files), json.dumps(thermal_zones), status))

    def get_latest_monitoring_record(self, device_ip):
        rows = self.execute_query(
            'SELECT * FROM monitoring_history WHERE device_ip = ? ORDER BY check_time DESC LIMIT 1', (device_ip,)
        )
        if rows:
            d = dict(rows[0])
            d['high_memory_processes'] = json.loads(d['high_memory_processes'] or '[]')
            d['new_core_files'] = json.loads(d['new_core_files'] or '[]')
            d['thermal_zones'] = json.loads(d['thermal_zones'] or '[]')
            return d
        return {}

    def get_latest_monitoring_records_batch(self, device_ips):
        """批量获取多个设备的最新监控记录（优化版：一次查询替代N次）"""
        if not device_ips:
            return {}

        # 使用 IN 查询一次获取所有设备的最新记录
        placeholders = ','.join(['?'] * len(device_ips))
        sql = f'''
            SELECT * FROM monitoring_history
            WHERE (device_ip, check_time) IN (
                SELECT device_ip, MAX(check_time)
                FROM monitoring_history
                WHERE device_ip IN ({placeholders})
                GROUP BY device_ip
            )
        '''
        rows = self.execute_query(sql, tuple(device_ips))

        result = {}
        for row in rows:
            d = dict(row)
            d['high_memory_processes'] = json.loads(d['high_memory_processes'] or '[]')
            d['new_core_files'] = json.loads(d['new_core_files'] or '[]')
            d['thermal_zones'] = json.loads(d['thermal_zones'] or '[]')
            result[d['device_ip']] = d
        return result

    def get_device_stats(self, device_ip, hours=24):
        """获取统计数据 (修复版)"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            time_filter = f'-{hours} hours'

            cursor.execute(
                "SELECT COUNT(*) FROM monitoring_history WHERE device_ip=? AND check_time >= datetime('now', 'localtime', ?)",
                (device_ip, time_filter))
            total = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM monitoring_history WHERE device_ip=? AND status='online' AND check_time >= datetime('now', 'localtime', ?)",
                (device_ip, time_filter))
            online = cursor.fetchone()[0]
            rate = (online / total * 100) if total > 0 else 0

            cursor.execute(
                "SELECT AVG(memory_usage) FROM monitoring_history WHERE device_ip=? AND status='online' AND check_time >= datetime('now', 'localtime', ?)",
                (device_ip, time_filter))
            res = cursor.fetchone()
            mem = res[0] if res and res[0] else 0

            cursor.execute(
                "SELECT COUNT(*) FROM alerts WHERE device_ip=? AND alert_time >= datetime('now', 'localtime', ?)",
                (device_ip, time_filter))
            alerts = cursor.fetchone()[0]

            return {'online_rate': round(rate, 2), 'avg_memory_usage': round(mem, 2), 'total_alerts': alerts,
                    'total_checks': total}
        except Exception as e:
            logger.error(f"统计异常: {e}")
            return {'online_rate': 0, 'avg_memory_usage': 0, 'total_alerts': 0, 'total_checks': 0}
        finally:
            conn.close()

    # =======================================================
    # 业务方法：告警与筛选
    # =======================================================

    def add_alert(self, device_ip, alert_type, alert_message):
        return self.execute_command(
            "INSERT INTO alerts (device_ip, alert_type, alert_message) VALUES (?, ?, ?)",
            (device_ip, alert_type, alert_message)
        )

    def query_alerts(self, start_time=None, end_time=None, product_line=None, alert_type=None, ip=None):
        """告警筛选 (已适配 product_line)"""
        sql = '''
            SELECT a.id, a.device_ip, a.alert_time, a.alert_type, a.alert_message, d.product_line
            FROM alerts a LEFT JOIN devices d ON a.device_ip = d.ip
            WHERE 1 = 1
        '''
        params = []
        if start_time:
            sql += " AND a.alert_time >= ?"
            params.append(start_time)
        if end_time:
            sql += " AND a.alert_time <= ?"
            params.append(end_time)

        # 筛选 product_line
        if product_line and product_line != '全部':
            sql += " AND d.product_line = ?"
            params.append(product_line)

        if alert_type and alert_type != '全部':
            sql += " AND a.alert_type = ?"
            params.append(alert_type)
        if ip:
            sql += " AND a.device_ip LIKE ?"
            params.append(f"%{ip}%")

        sql += " ORDER BY a.alert_time DESC LIMIT 500"

        rows = self.execute_query(sql, tuple(params))
        return [
            {
                'id': r[0], 'ip': r[1], 'time': r[2], 'type': r[3], 'message': r[4],
                'product_line': r[5] or '未分类'
            }
            for r in rows
        ]

    def get_alert_types(self):
        rows = self.execute_query("SELECT DISTINCT alert_type FROM alerts")
        return [row[0] for row in rows if row[0]]

    def batch_delete_alerts(self, days=None, ip=None, alert_type=None, delete_all=False):
        """批量删除告警
        - days: 删除多少天之前的告警（如7删除7天前的）
        - ip: 删除指定IP的告警
        - alert_type: 删除指定类型的告警
        - delete_all: 是否删除所有告警
        """
        if delete_all:
            self.execute_command("DELETE FROM alerts", ())
            return 0

        sql = "DELETE FROM alerts WHERE 1=1"
        params = []

        if days:
            sql += " AND alert_time < datetime('now', ?, 'localtime')"
            params.append(f"-{days} days")

        if ip:
            sql += " AND device_ip = ?"
            params.append(ip)

        if alert_type:
            sql += " AND alert_type = ?"
            params.append(alert_type)

        if not days and not ip and not alert_type:
            return 0

        self.execute_command(sql, tuple(params))
        return 0

    def delete_alerts_by_ids(self, ids):
        """按ID删除告警"""
        if not ids:
            return 0
        placeholders = ','.join('?' * len(ids))
        self.execute_command(f"DELETE FROM alerts WHERE id IN ({placeholders})", ids)
        return len(ids)

    def get_product_lines(self):
        rows = self.execute_query("SELECT DISTINCT product_line FROM devices")
        return [row[0] for row in rows if row[0]]

    # =======================================================
    # 业务方法：温度测试
    # =======================================================

    def create_temperature_test(self, device_ip, test_phase, test_duration, threshold_memory_pct, threshold_temp_pct, baseline_id=None):
        """创建温度测试"""
        self.execute_command(
            """INSERT INTO temperature_tests
               (device_ip, test_phase, test_duration, threshold_memory_pct, threshold_temp_pct, baseline_id, start_time, status)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), 'running')""",
            (device_ip, test_phase, test_duration, threshold_memory_pct, threshold_temp_pct, baseline_id)
        )
        return self.execute_query("SELECT last_insert_rowid()")[0][0]

    def stop_temperature_test(self, test_id):
        """停止温度测试"""
        self.execute_command(
            "UPDATE temperature_tests SET status='stopped', end_time=datetime('now', 'localtime') WHERE id=?",
            (test_id,)
        )

    def complete_temperature_test(self, test_id):
        """完成温度测试"""
        self.execute_command(
            "UPDATE temperature_tests SET status='completed', end_time=datetime('now', 'localtime') WHERE id=?",
            (test_id,)
        )

    def get_temperature_test(self, test_id):
        """获取温度测试详情"""
        rows = self.execute_query("SELECT * FROM temperature_tests WHERE id=?", (test_id,))
        return dict(rows[0]) if rows else None

    def get_temperature_tests(self, device_ip=None, status=None):
        """获取温度测试列表"""
        sql = "SELECT * FROM temperature_tests WHERE 1=1"
        params = []
        if device_ip:
            sql += " AND device_ip=?"
            params.append(device_ip)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_time DESC"
        return [dict(row) for row in self.execute_query(sql, tuple(params))]

    def add_temperature_test_data(self, test_id, process_data, memory_usage, memory_delta_pct,
                                   thermal_zones, thermal_delta_pct, process_restarts, core_files, exceptions):
        """添加温度测试数据"""
        import json
        self.execute_command(
            """INSERT INTO temperature_test_data
               (test_id, process_data, memory_usage, memory_delta_pct, thermal_zones, thermal_delta_pct,
                process_restarts, core_files, exceptions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (test_id,
             json.dumps(process_data, ensure_ascii=False) if process_data else None,
             memory_usage, memory_delta_pct,
             json.dumps(thermal_zones, ensure_ascii=False) if thermal_zones else None,
             thermal_delta_pct,
             json.dumps(process_restarts, ensure_ascii=False) if process_restarts else None,
             json.dumps(core_files, ensure_ascii=False) if core_files else None,
             json.dumps(exceptions, ensure_ascii=False) if exceptions else None)
        )

    def get_temperature_test_data(self, test_id):
        """获取温度测试数据"""
        rows = self.execute_query(
            "SELECT * FROM temperature_test_data WHERE test_id=? ORDER BY check_time",
            (test_id,)
        )
        import json
        result = []
        for row in rows:
            r = dict(row)
            r['process_data'] = json.loads(r['process_data']) if r['process_data'] else []
            r['thermal_zones'] = json.loads(r['thermal_zones']) if r['thermal_zones'] else []
            r['process_restarts'] = json.loads(r['process_restarts']) if r['process_restarts'] else []
            r['core_files'] = json.loads(r['core_files']) if r['core_files'] else []
            r['exceptions'] = json.loads(r['exceptions']) if r['exceptions'] else []
            result.append(r)
        return result

    def get_running_temperature_tests(self):
        """获取正在进行的温度测试"""
        rows = self.execute_query(
            "SELECT * FROM temperature_tests WHERE status='running'"
        )
        return [dict(row) for row in rows]

    def get_baseline_tests(self, device_ip):
        """获取常温基准测试列表"""
        rows = self.execute_query(
            "SELECT * FROM temperature_tests WHERE device_ip=? AND test_phase='baseline' AND status='completed' ORDER BY created_time DESC",
            (device_ip,)
        )
        return [dict(row) for row in rows]

    def delete_temperature_test(self, test_id):
        """删除温度测试记录（同时删除相关数据）"""
        # 先删除测试数据
        self.execute_command("DELETE FROM temperature_test_data WHERE test_id=?", (test_id,))
        # 再删除测试记录
        self.execute_command("DELETE FROM temperature_tests WHERE id=?", (test_id,))

    # =======================================================
    # 业务方法：内存分析
    # =======================================================

    def get_process_memory_history(self, device_ip, process_name, days=7):
        """获取进程内存历史数据"""
        rows = self.execute_query("""
            SELECT high_memory_processes, check_time FROM monitoring_history
            WHERE device_ip = ? AND check_time >= datetime('now', ?, 'localtime')
            ORDER BY check_time
        """, (device_ip, f"-{days} days"))
        return [dict(row) for row in rows]

    def save_memory_analysis(self, device_ip, process_name, analysis_date, max_memory, avg_memory,
                            p95_memory, std_memory, data_points, growth_rate, trend_status,
                            recommended_memory, alert_message):
        """保存内存分析结果"""
        self.execute_command("""
            INSERT OR REPLACE INTO memory_analysis
            (device_ip, process_name, analysis_date, max_memory, avg_memory, p95_memory, std_memory,
             data_points, growth_rate, trend_status, recommended_memory, alert_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (device_ip, process_name, analysis_date, max_memory, avg_memory, p95_memory, std_memory,
              data_points, growth_rate, trend_status, recommended_memory, alert_message))

    def get_memory_analysis_results(self, device_ip=None, days=30):
        """获取内存分析结果"""
        sql = "SELECT * FROM memory_analysis WHERE analysis_date >= datetime('now', ?, 'localtime')"
        params = [f"-{days} days"]
        if device_ip:
            sql += " AND device_ip = ?"
            params.append(device_ip)
        sql += " ORDER BY analysis_date DESC, max_memory DESC"
        return [dict(row) for row in self.execute_query(sql, tuple(params))]

    def delete_memory_analysis(self, id):
        """删除内存分析记录"""
        self.execute_command("DELETE FROM memory_analysis WHERE id=?", (id,))

    def delete_all_memory_analysis(self, device_ip=None):
        """删除所有内存分析记录"""
        if device_ip:
            self.execute_command("DELETE FROM memory_analysis WHERE device_ip=?", (device_ip,))
        else:
            self.execute_command("DELETE FROM memory_analysis")

    def create_analysis_log(self):
        """创建分析任务日志"""
        self.execute_command(
            "INSERT INTO memory_analysis_log (start_time, status) VALUES (datetime('now', 'localtime'), 'running')"
        )
        return self.execute_query("SELECT last_insert_rowid()")[0][0]

    def finish_analysis_log(self, log_id, status, summary, alerts):
        """更新分析任务日志"""
        self.execute_command(
            """UPDATE memory_analysis_log
               SET end_time=datetime('now', 'localtime'), status=?, summary=?, alerts=?
               WHERE id=?""",
            (status, summary, alerts, log_id)
        )

    def get_latest_analysis_log(self):
        """获取最近的分析日志"""
        rows = self.execute_query(
            "SELECT * FROM memory_analysis_log ORDER BY created_time DESC LIMIT 1"
        )
        return dict(rows[0]) if rows else None

    def update_process_allocated_memory(self, device_ip, process_name, allocated_memory):
        """更新进程的分配内存阈值"""
        self.execute_command(
            """UPDATE custom_risk_processes
               SET allocated_memory = ?
               WHERE device_ip = ? AND process_name = ?""",
            (allocated_memory, device_ip, process_name)
        )

    # =======================================================
    # 业务方法：网络监控
    # =======================================================

    def add_network_stats(self, device_ip, interface, rx_bytes, tx_bytes, rx_rate, tx_rate, bandwidth_mbps, latency_ms, packet_loss):
        """保存网络监控数据"""
        self.execute_command(
            """INSERT INTO network_stats
               (device_ip, interface, rx_bytes, tx_bytes, rx_rate, tx_rate, bandwidth_mbps, latency_ms, packet_loss)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (device_ip, interface, rx_bytes, tx_bytes, rx_rate, tx_rate, bandwidth_mbps, latency_ms, packet_loss)
        )

    def get_network_stats(self, device_ip, limit=100):
        """获取网络监控历史"""
        rows = self.execute_query(
            """SELECT * FROM network_stats WHERE device_ip = ? ORDER BY check_time DESC LIMIT ?""",
            (device_ip, limit)
        )
        return [dict(row) for row in rows]

    def get_latest_network_stats(self, device_ip):
        """获取最新网络监控数据"""
        rows = self.execute_query(
            """SELECT * FROM network_stats WHERE device_ip = ? ORDER BY check_time DESC LIMIT 1""",
            (device_ip,)
        )
        return dict(rows[0]) if rows else None

    def get_all_processes_from_history(self, days=7):
        """从历史数据获取所有进程"""
        rows = self.execute_query("""
            SELECT DISTINCT device_ip, high_memory_processes
            FROM monitoring_history
            WHERE check_time >= datetime('now', ?, 'localtime')
              AND high_memory_processes IS NOT NULL
              AND high_memory_processes != ''
        """, (f"-{days} days"))

        result = {}
        import json
        for row in rows:
            ip = row[0]
            try:
                processes = json.loads(row[1]) if row[1] else []
            except:
                processes = []
            if ip not in result:
                result[ip] = {}
            for proc in processes:
                if isinstance(proc, dict):
                    name = proc.get('command') or proc.get('name')
                    if name:
                        result[ip][name] = True
        return result

    def add_core_file_record(self, device_ip, filename, timestamp, filesize):
        return self.execute_command(
            "INSERT OR IGNORE INTO core_files (device_ip, filename, timestamp, filesize) VALUES (?, ?, ?, ?)",
            (device_ip, filename, timestamp, filesize)
        )

    def get_custom_risk_processes(self, device_ip):
        return [dict(row) for row in
                self.execute_query("SELECT * FROM custom_risk_processes WHERE device_ip = ?", (device_ip,))]

    def add_custom_risk_process(self, device_ip, pid, process_name, allocated_memory, source='manual'):
        return self.execute_command(
            "INSERT INTO custom_risk_processes (device_ip, pid, process_name, allocated_memory, source) VALUES (?, ?, ?, ?, ?)",
            (device_ip, pid, process_name, allocated_memory, source)
        )

    def add_or_update_auto_process(self, device_ip, pid, process_name, current_memory, mem_pct):
        """自动发现的进程：存在则更新，不存在则插入"""
        existing = self.execute_query(
            "SELECT id FROM custom_risk_processes WHERE device_ip = ? AND process_name = ? AND source = 'auto'",
            (device_ip, process_name)
        )
        if existing:
            # 更新
            return self.execute_command(
                """UPDATE custom_risk_processes SET pid=?, current_memory=?, memory_usage_percent=?,
                   last_check_time=datetime('now', 'localtime') WHERE device_ip=? AND process_name=? AND source='auto'""",
                (pid, current_memory, mem_pct, device_ip, process_name)
            )
        else:
            # 插入（allocated_memory设为0表示自动发现）
            return self.execute_command(
                "INSERT INTO custom_risk_processes (device_ip, pid, process_name, allocated_memory, current_memory, memory_usage_percent, source) VALUES (?, ?, ?, 0, ?, ?, 'auto')",
                (device_ip, pid, process_name, current_memory, mem_pct)
            )

    def delete_custom_risk_process(self, id):
        return self.execute_command("DELETE FROM custom_risk_processes WHERE id = ?", (id,))

    def update_custom_risk_process_status(self, id, current_mem, mem_pct, status, alert, new_pid=None):
        if new_pid:
            return self.execute_command('''
                UPDATE custom_risk_processes
                SET current_memory=?, memory_usage_percent=?, status=?, alert_triggered=?, pid=?, last_check_time=datetime('now', 'localtime')
                WHERE id = ?
            ''', (current_mem, mem_pct, status, alert, str(new_pid), id))
        else:
            return self.execute_command('''
                UPDATE custom_risk_processes
                SET current_memory=?, memory_usage_percent=?, status=?, alert_triggered=?, last_check_time=datetime('now', 'localtime')
                WHERE id = ?
            ''', (current_mem, mem_pct, status, alert, id))

    # =======================================================
    # 业务方法：模型评估
    # =======================================================

    def save_model_evaluation(self, device_ip, process_name, evaluation_date, data_points, train_size,
                            test_size, r2_score, mae, rmse, mape, max_ae, predicted_trend, actual_trend,
                            trend_correct, recommended_memory, predicted_max, actual_max):
        """保存模型评估结果"""
        self.execute_command("""
            INSERT OR REPLACE INTO model_evaluations
            (device_ip, process_name, evaluation_date, data_points, train_size, test_size,
             r2_score, mae, rmse, mape, max_ae, predicted_trend, actual_trend,
             trend_correct, recommended_memory, predicted_max, actual_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (device_ip, process_name, evaluation_date, data_points, train_size, test_size,
              r2_score, mae, rmse, mape, max_ae, predicted_trend, actual_trend,
              trend_correct, recommended_memory, predicted_max, actual_max))

    def get_model_evaluations(self, device_ip=None, process_name=None, days=30):
        """获取模型评估历史"""
        sql = """SELECT * FROM model_evaluations WHERE evaluation_date >= datetime('now', ?, 'localtime')"""
        params = [f"-{days} days"]
        if device_ip:
            sql += " AND device_ip = ?"
            params.append(device_ip)
        if process_name:
            sql += " AND process_name = ?"
            params.append(process_name)
        sql += " ORDER BY evaluation_date DESC"
        return [dict(row) for row in self.execute_query(sql, tuple(params))]

    def get_model_evaluation_summary(self, days=30):
        """获取模型评估概览统计"""
        rows = self.execute_query("""
            SELECT
                COUNT(*) as total,
                AVG(r2_score) as avg_r2,
                AVG(mae) as avg_mae,
                AVG(rmse) as avg_rmse,
                AVG(mape) as avg_mape,
                AVG(CASE WHEN trend_correct = 1 THEN 100.0 ELSE 0.0 END) as trend_accuracy,
                SUM(CASE WHEN r2_score >= 0.7 THEN 1 ELSE 0 END) as good_count,
                SUM(CASE WHEN r2_score >= 0.5 AND r2_score < 0.7 THEN 1 ELSE 0 END) as normal_count,
                SUM(CASE WHEN r2_score < 0.5 OR r2_score IS NULL THEN 1 ELSE 0 END) as poor_count
            FROM model_evaluations
            WHERE evaluation_date >= datetime('now', ?, 'localtime')
        """, (f"-{days} days",))
        if rows and rows[0]:
            row = rows[0]
            return {
                'total': row[0] or 0,
                'avg_r2': round(row[1], 4) if row[1] else 0,
                'avg_mae': round(row[2], 2) if row[2] else 0,
                'avg_rmse': round(row[3], 2) if row[3] else 0,
                'avg_mape': round(row[4], 2) if row[4] else 0,
                'trend_accuracy': round(row[5], 1) if row[5] else 0,
                'good_count': row[6] or 0,
                'normal_count': row[7] or 0,
                'poor_count': row[8] or 0
            }
        return {'total': 0, 'avg_r2': 0, 'avg_mae': 0, 'avg_rmse': 0, 'avg_mape': 0, 'trend_accuracy': 0}

    def get_model_evaluation_trend(self, days=30):
        """获取评估趋势数据（用于图表）"""
        rows = self.execute_query("""
            SELECT
                DATE(evaluation_date) as date,
                AVG(r2_score) as avg_r2,
                AVG(mae) as avg_mae,
                AVG(mape) as avg_mape
            FROM model_evaluations
            WHERE evaluation_date >= datetime('now', ?, 'localtime')
            GROUP BY DATE(evaluation_date)
            ORDER BY date ASC
        """, (f"-{days} days",))
        return [
            {
                'date': row[0],
                'avg_r2': round(row[1], 4) if row[1] else 0,
                'avg_mae': round(row[2], 2) if row[2] else 0,
                'avg_mape': round(row[3], 2) if row[3] else 0
            }
            for row in rows
        ]

    def save_prediction_error(self, device_ip, process_name, prediction_date, check_date, predicted_value, actual_value):
        """保存预测误差"""
        error_pct = abs(predicted_value - actual_value) / actual_value * 100 if actual_value > 0 else 0
        self.execute_command("""
            INSERT INTO prediction_errors
            (device_ip, process_name, prediction_date, check_date, predicted_value, actual_value, error_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (device_ip, process_name, prediction_date, check_date, predicted_value, actual_value, error_pct))

    def get_prediction_errors(self, device_ip=None, process_name=None, days=30):
        """获取预测误差记录"""
        sql = """SELECT * FROM prediction_errors WHERE check_date >= datetime('now', ?, 'localtime')"""
        params = [f"-{days} days"]
        if device_ip:
            sql += " AND device_ip = ?"
            params.append(device_ip)
        if process_name:
            sql += " AND process_name = ?"
            params.append(process_name)
        sql += " ORDER BY check_date DESC"
        return [dict(row) for row in self.execute_query(sql, tuple(params))]