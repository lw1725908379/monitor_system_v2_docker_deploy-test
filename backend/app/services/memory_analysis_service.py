import json
import logging
import statistics
from datetime import datetime, timedelta
from backend.shared.database import DatabaseManager
from backend.app.core.config import Config

logger = logging.getLogger(__name__)


class MemoryAnalysisService:
    """内存分析服务 - AIOps智能运维"""

    def __init__(self, days=7):
        self.db = DatabaseManager(Config.DB_PATH)
        self.days = days

        # 趋势判断阈值（可配置）
        self.LEAK_THRESHOLD = 1.0  # MB/小时，增长超过此值疑似泄漏
        self.DOWN_THRESHOLD = -1.0  # MB/小时，下降超过此值

    def run_analysis(self):
        """执行内存分析主流程"""
        log_id = self.db.create_analysis_log()
        logger.info(f"开始内存分析任务: log_id={log_id}")

        try:
            # 1. 获取所有设备
            devices = self.db.get_all_devices()
            all_results = []
            all_alerts = []

            for device in devices:
                device_ip = device['ip']
                logger.info(f"分析设备: {device_ip}")

                # 2. 获取该设备的所有进程
                processes = self._get_device_processes(device_ip)

                for process_name in processes:
                    # 3. 分析每个进程
                    result = self.analyze_process(device_ip, process_name)
                    if result:
                        all_results.append(result)

                        # 保存到数据库
                        self.db.save_memory_analysis(
                            device_ip=device_ip,
                            process_name=process_name,
                            analysis_date=datetime.now().strftime('%Y-%m-%d'),
                            max_memory=result['max_memory'],
                            avg_memory=result['avg_memory'],
                            p95_memory=result['p95_memory'],
                            std_memory=result['std_memory'],
                            data_points=result['data_points'],
                            growth_rate=result['growth_rate'],
                            trend_status=result['trend_status'],
                            recommended_memory=result['recommended_memory'],
                            alert_message=result.get('alert_message')
                        )

                        # 4. 如果有告警，记录下来
                        if result.get('alert_message'):
                            all_alerts.append({
                                'ip': device_ip,
                                'process': process_name,
                                'message': result['alert_message']
                            })

                        # 5. 更新进程的监控阈值
                        if result['recommended_memory']:
                            self.db.update_process_allocated_memory(
                                device_ip, process_name, result['recommended_memory']
                            )
                            logger.info(f"更新进程监控阈值: {device_ip}/{process_name} -> {result['recommended_memory']}MB")

            # 完成任务
            summary = f"共分析 {len(devices)} 台设备, {len(all_results)} 个进程, {len(all_alerts)} 个异常"
            self.db.finish_analysis_log(log_id, 'completed', summary, json.dumps(all_alerts, ensure_ascii=False))
            logger.info(f"内存分析完成: {summary}")

            return {'success': True, 'summary': summary, 'alerts': all_alerts}

        except Exception as e:
            logger.error(f"内存分析失败: {e}", exc_info=True)
            self.db.finish_analysis_log(log_id, 'failed', str(e), '[]')
            return {'success': False, 'error': str(e)}

    def _get_device_processes(self, device_ip):
        """获取设备的所有进程名"""
        # 从监控历史中获取进程
        rows = self.db.execute_query("""
            SELECT DISTINCT high_memory_processes
            FROM monitoring_history
            WHERE device_ip = ? AND check_time >= datetime('now', ?, 'localtime')
              AND high_memory_processes IS NOT NULL AND high_memory_processes != ''
        """, (device_ip, f"-{self.days} days"))

        processes = set()
        for row in rows:
            try:
                data = json.loads(row[0]) if row[0] else []
                for proc in data:
                    if isinstance(proc, dict):
                        name = proc.get('command') or proc.get('name')
                        if name:
                            processes.add(name)
            except:
                continue

        return list(processes)

    def analyze_process(self, device_ip, process_name):
        """分析单个进程的内存使用"""
        try:
            # 1. 获取历史数据
            rows = self.db.execute_query("""
                SELECT high_memory_processes, check_time
                FROM monitoring_history
                WHERE device_ip = ? AND check_time >= datetime('now', ?, 'localtime')
                ORDER BY check_time
            """, (device_ip, f"-{self.days} days"))

            memory_data = []
            for row in rows:
                try:
                    data = json.loads(row[0]) if row[0] else []
                except:
                    data = []

                # 找到该进程的数据
                for proc in data:
                    if isinstance(proc, dict):
                        name = proc.get('command') or proc.get('name')
                        if name == process_name:
                            mem_kb = proc.get('rss_kb', 0)
                            if mem_kb > 0:  # 过滤无效数据
                                memory_data.append({
                                    'memory_mb': mem_kb / 1024,
                                    'time': row[1]
                                })
                            break

            # 需要足够的数据点
            if len(memory_data) < 10:
                return None

            # 2. 统计特征计算
            memories = [d['memory_mb'] for d in memory_data]

            # 处理离群点（超过均值3倍标准差）
            if len(memories) > 10:
                mean = statistics.mean(memories)
                stdev = statistics.stdev(memories) if len(memories) > 1 else 0
                if stdev > 0:
                    memories = [m for m in memories if abs(m - mean) <= 3 * stdev]

            if len(memories) < 5:
                return None

            max_memory = max(memories)
            avg_memory = statistics.mean(memories)
            p95_memory = self._percentile(memories, 95)
            std_memory = statistics.stdev(memories) if len(memories) > 1 else 0

            # 3. 趋势分析（线性回归）
            growth_rate = self._calculate_growth_rate(memory_data)

            # 判断趋势状态
            if growth_rate > self.LEAK_THRESHOLD:
                trend_status = 'leak'
            elif growth_rate < self.DOWN_THRESHOLD:
                trend_status = 'down'
            else:
                trend_status = 'stable'

            # 4. 推荐值计算
            recommended_memory = int(p95_memory * 1.2)
            if recommended_memory < max_memory:
                recommended_memory = int(max_memory * 1.1)

            # 5. 告警消息
            alert_message = None
            if trend_status == 'leak':
                alert_message = f"疑似内存泄漏: 增长率 {growth_rate:.2f} MB/小时"
            elif trend_status == 'down':
                alert_message = f"内存下降趋势: {growth_rate:.2f} MB/小时"

            return {
                'process_name': process_name,
                'max_memory': round(max_memory, 2),
                'avg_memory': round(avg_memory, 2),
                'p95_memory': round(p95_memory, 2),
                'std_memory': round(std_memory, 2),
                'data_points': len(memory_data),
                'growth_rate': round(growth_rate, 4),
                'trend_status': trend_status,
                'recommended_memory': recommended_memory,
                'alert_message': alert_message
            }

        except Exception as e:
            logger.error(f"分析进程 {device_ip}/{process_name} 失败: {e}")
            return None

    def _percentile(self, data, p):
        """计算百分位数"""
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)

    def _calculate_growth_rate(self, memory_data):
        """通过线性回归计算增长率（MB/小时）"""
        if len(memory_data) < 2:
            return 0

        # 转换为时间戳（小时）
        base_time = datetime.fromisoformat(memory_data[0]['time'].replace(' ', 'T'))
        points = []
        for d in memory_data:
            try:
                t = datetime.fromisoformat(d['time'].replace(' ', 'T'))
                hours = (t - base_time).total_seconds() / 3600
                points.append((hours, d['memory_mb']))
            except:
                continue

        if len(points) < 2:
            return 0

        # 简单线性回归
        n = len(points)
        sum_x = sum(p[0] for p in points)
        sum_y = sum(p[1] for p in points)
        sum_xy = sum(p[0] * p[1] for p in points)
        sum_x2 = sum(p[0] ** 2 for p in points)

        denominator = n * sum_x2 - sum_x ** 2
        if denominator == 0:
            return 0

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        return slope
