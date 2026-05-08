import os
import json
from datetime import datetime
from backend.shared.database import DatabaseManager
from backend.app.core.config import Config
from backend.app.utils.logger import logger


class ReportService:
    def __init__(self):
        self.db = DatabaseManager(Config.DB_PATH)
        self.report_dir = Config.REPORT_DIR
        # 确保报告目录存在
        os.makedirs(self.report_dir, exist_ok=True)

    def generate_daily_report(self):
        return self._generate_report(days=1, type_name="daily")

    def generate_weekly_report(self):
        return self._generate_report(days=7, type_name="weekly")

    def _generate_report(self, days, type_name):
        logger.info(f"开始生成 {type_name} 报表...")
        try:
            # 1. 收集数据
            data = self._collect_data(days)
            date_str = datetime.now().strftime('%Y%m%d')

            # 2. 保存 JSON (可选，作为数据备份)
            json_filename = f"{type_name}_report_{date_str}.json"
            json_path = os.path.join(self.report_dir, json_filename)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 3. 生成 HTML
            html_content = self._render_html(data, type_name)
            html_filename = f"{type_name}_report_{date_str}.html"
            html_path = os.path.join(self.report_dir, html_filename)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.info(f"报表生成成功: {html_path}")
            return {'json_path': json_path, 'html_path': html_path}
        except Exception as e:
            logger.error(f"报表生成失败: {e}", exc_info=True)
            raise e

    def _collect_data(self, days):
        """从数据库收集统计数据"""
        devices = self.db.get_all_devices()
        report_data = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "period_days": days,
            "total_devices": len(devices),
            "devices": []
        }

        for dev in devices:
            ip = dev['ip']
            # 获取统计信息
            stats = self.db.get_device_stats(ip, hours=days * 24)
            latest = self.db.get_latest_monitoring_record(ip)

            # 这里的字段名要与数据库查询结果一致
            report_data["devices"].append({
                "ip": ip,
                # 【修改】使用 product_line
                "product_line": dev.get('product_line', '未分类'),
                "online_rate": stats.get('online_rate', 0),
                "avg_memory": stats.get('avg_memory_usage', 0),
                "alerts_count": stats.get('total_alerts', 0),
                "status": latest.get('status', 'unknown')
            })

        return report_data

    def _render_html(self, data, type_name):
        """渲染 HTML 报表"""
        title = "日报" if type_name == "daily" else "周报"

        # 构建表格行
        rows = ""
        for d in data['devices']:
            status_color = "green" if d['status'] == 'online' else "red"
            rows += f"""
            <tr>
                <td>{d['ip']}</td>
                <!-- 【修改】显示产品线 -->
                <td>{d['product_line']}</td>
                <td style="color:{status_color}">{d['status']}</td>
                <td>{d['online_rate']}%</td>
                <td>{d['avg_memory']}%</td>
                <td>{d['alerts_count']}</td>
            </tr>
            """

        # 完整 HTML 模板
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>设备监控{title}</title>
            <style>
                body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; padding: 20px; }}
                h1 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
                .meta {{ color: #666; margin-bottom: 20px; background: #f8f9fa; padding: 15px; border-radius: 5px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #007bff; color: white; }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
                tr:hover {{ background-color: #f1f1f1; }}
            </style>
        </head>
        <body>
            <h1>设备监控{title}</h1>
            <div class="meta">
                <strong>生成时间:</strong> {data['generated_at']}<br>
                <strong>统计周期:</strong> 过去 {data['period_days']} 天<br>
                <strong>设备总数:</strong> {data['total_devices']} 台
            </div>
            <table>
                <thead>
                    <tr>
                        <th>IP地址</th>
                        <th>产品线</th> <!-- 【修改】表头 -->
                        <th>当前状态</th>
                        <th>在线率</th>
                        <th>平均内存</th>
                        <th>告警数</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </body>
        </html>
        """
        return html