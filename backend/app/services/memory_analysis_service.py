import json
import logging
import statistics
import numpy as np
from datetime import datetime, timedelta
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from backend.shared.database import DatabaseManager
from backend.app.core.config import Config

logger = logging.getLogger(__name__)


class MemoryAnalysisService:
    """内存分析服务 - AIOps智能运维"""

    def __init__(self, days=7):
        self.db = DatabaseManager(Config.DB_PATH)
        self.days = days
        ml_config = Config.ML_MODEL_CONFIG
        self.ridge_alpha = ml_config.get('ridge_alpha', 1.0)
        self.prediction_steps = ml_config.get('prediction_steps', 120)
        self.min_data_points = ml_config.get('min_data_points', 50)
        self.safety_margin = ml_config.get('safety_margin', {'stable': 5, 'up': 10, 'leak': 15})
        trend_cfg = ml_config.get('trend_threshold', {})
        self.LEAK_THRESHOLD = trend_cfg.get('leak', 1.0)
        self.DOWN_THRESHOLD = trend_cfg.get('down', -1.0)
        # 评估配置
        self.test_size_ratio = ml_config.get('test_size_ratio', 0.2)
        self.enable_evaluation = ml_config.get('enable_evaluation', True)

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

            # 4. 推荐值计算 - Ridge回归模型预测
            recommended_memory, evaluation = self._calculate_recommended_with_ridge(memory_data, trend_status)

            # 5. 保存评估结果到数据库
            if evaluation:
                self.db.save_model_evaluation(
                    device_ip=device_ip,
                    process_name=process_name,
                    evaluation_date=datetime.now().strftime('%Y-%m-%d'),
                    data_points=evaluation['data_points'],
                    train_size=evaluation['train_size'],
                    test_size=evaluation['test_size'],
                    r2_score=evaluation['r2_score'],
                    mae=evaluation['mae'],
                    rmse=evaluation['rmse'],
                    mape=evaluation['mape'],
                    max_ae=evaluation['max_ae'],
                    predicted_trend=evaluation['predicted_trend'],
                    actual_trend=evaluation['actual_trend'],
                    trend_correct=1 if evaluation['trend_correct'] else 0,
                    recommended_memory=recommended_memory,
                    predicted_max=evaluation['predicted_max'],
                    actual_max=evaluation['actual_max']
                )

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
                'alert_message': alert_message,
                'evaluation': evaluation
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

    def _calculate_recommended_with_ridge(self, memory_data, trend_status):
        """使用Ridge回归模型预测推荐阈值，并进行模型评估"""
        if len(memory_data) < self.min_data_points:
            # 数据不足，使用简单统计方法
            memories = [d['memory_mb'] for d in memory_data]
            p95 = self._percentile(memories, 95)
            max_mem = max(memories)
            return int(max(p95 * 1.2, max_mem * 1.1)), None

        # 1. 构建特征矩阵
        memories = [d['memory_mb'] for d in memory_data]
        n = len(memories)

        # 特征: 时间步、移动平均、斜率、波动性、最近增长
        time_steps = np.arange(1, n + 1).reshape(-1, 1)
        ma = self._moving_average(memories, 7)
        slopes = np.array([self._calculate_local_slope(memories, i) for i in range(n)])
        stds = np.array([self._calculate_local_std(memories, i) for i in range(n)])
        recent_growth = np.array([memories[i] - memories[0] for i in range(n)])

        # 构建特征矩阵
        X = np.column_stack([time_steps, ma, slopes, stds, recent_growth])
        y = np.array(memories)

        # 评估指标初始化
        evaluation_result = None
        actual_max = max(memories)

        # 2. 数据划分与模型评估
        if self.enable_evaluation and n >= 10:
            test_size = max(1, int(n * self.test_size_ratio))
            train_size = n - test_size

            X_train, X_test = X[:train_size], X[train_size:]
            y_train, y_test = y[:train_size], y[train_size:]

            # 训练评估模型
            eval_model = Ridge(alpha=self.ridge_alpha)
            eval_model.fit(X_train, y_train)

            # 测试集预测
            y_pred = eval_model.predict(X_test)

            # 计算评估指标
            mae = mean_absolute_error(y_test, y_pred)
            rmse = np.sqrt(mean_squared_error(y_test, y_pred))
            r2 = r2_score(y_test, y_pred)

            # 计算 MAPE（避免除零）
            non_zero_mask = y_test != 0
            if np.any(non_zero_mask):
                mape = np.mean(np.abs((y_test[non_zero_mask] - y_pred[non_zero_mask]) / y_test[non_zero_mask])) * 100
            else:
                mape = 0

            # 最大绝对误差
            max_ae = np.max(np.abs(y_test - y_pred))

            # 预测趋势 vs 实际趋势
            predicted_trend = trend_status
            # 计算测试集的实际趋势
            if len(y_test) >= 2:
                test_slope = (y_test[-1] - y_test[0]) / len(y_test)
                if test_slope > self.LEAK_THRESHOLD:
                    actual_trend = 'leak'
                elif test_slope < self.DOWN_THRESHOLD:
                    actual_trend = 'down'
                else:
                    actual_trend = 'stable'
            else:
                actual_trend = trend_status

            trend_correct = predicted_trend == actual_trend

            # 预测集最大值
            predicted_max = max(y_pred) if len(y_pred) > 0 else actual_max

            evaluation_result = {
                'data_points': n,
                'train_size': train_size,
                'test_size': test_size,
                'r2_score': round(r2, 4),
                'mae': round(mae, 2),
                'rmse': round(rmse, 2),
                'mape': round(mape, 2),
                'max_ae': round(max_ae, 2),
                'predicted_trend': predicted_trend,
                'actual_trend': actual_trend,
                'trend_correct': trend_correct,
                'predicted_max': round(predicted_max, 2),
                'actual_max': round(actual_max, 2)
            }

        # 3. 全量训练模型用于预测
        model = Ridge(alpha=self.ridge_alpha)
        model.fit(X, y)

        # 4. 预测未来N步
        future_steps = np.arange(n + 1, n + self.prediction_steps + 1).reshape(-1, 1)
        future_ma = np.array([self._moving_average(memories, 7)[-1]] * self.prediction_steps)
        future_slopes = np.array([slopes[-1]] * self.prediction_steps)
        future_stds = np.array([stds[-1]] * self.prediction_steps)
        recent_mem = memories[-1] - memories[0]
        future_recent = np.array([recent_mem] * self.prediction_steps)

        X_future = np.column_stack([future_steps, future_ma, future_slopes, future_stds, future_recent])
        predictions = model.predict(X_future)

        # 5. 计算推荐阈值
        predicted_future_max = max(predictions) if len(predictions) > 0 else actual_max
        actual_max = max(actual_max, predicted_future_max)

        # 根据趋势动态调整安全边际
        margin = self.safety_margin.get(trend_status, self.safety_margin['stable'])
        recommended = int(actual_max * (1 + margin / 100))

        result = max(recommended, int(max(memories) * 1.05))

        return result, evaluation_result

    def _moving_average(self, data, window):
        """计算移动平均"""
        if len(data) < window:
            return np.array([np.mean(data)] * len(data))
        result = []
        for i in range(len(data)):
            start = max(0, i - window + 1)
            result.append(np.mean(data[start:i + 1]))
        return np.array(result)

    def _calculate_local_slope(self, data, idx):
        """计算局部斜率"""
        window = min(10, idx + 1)
        if window < 2:
            return 0
        start = max(0, idx - window + 1)
        x = np.arange(window)
        y = np.array(data[start:idx + 1])
        if len(x) < 2:
            return 0
        return np.polyfit(x, y, 1)[0]

    def _calculate_local_std(self, data, idx):
        """计算局部标准差"""
        window = min(10, idx + 1)
        start = max(0, idx - window + 1)
        subset = data[start:idx + 1]
        if len(subset) < 2:
            return 0
        return np.std(subset)
