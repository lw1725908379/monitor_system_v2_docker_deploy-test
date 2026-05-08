from flask import Blueprint, jsonify, request, send_from_directory
from backend.app.services.report_service import ReportService
from backend.app.core.config import Config
import os
import datetime
report_bp = Blueprint('report', __name__, url_prefix='/api/report')
service = ReportService()


@report_bp.route('/list', methods=['GET'])
def list_reports():
    """列出所有已生成的报表"""
    reports = []
    if os.path.exists(Config.REPORT_DIR):
        for f in os.listdir(Config.REPORT_DIR):
            if f.endswith('.html') or f.endswith('.json'):
                path = os.path.join(Config.REPORT_DIR, f)
                stat = os.stat(path)

                create_time = datetime.datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')

                reports.append({
                    'filename': f,
                    'size': stat.st_size,
                    'created_at': create_time  # 返回格式化后的时间
                })

    reports.sort(key=lambda x: x['created_at'], reverse=True)

    return jsonify({'data': reports})


@report_bp.route('/generate', methods=['POST'])
def generate():
    """生成报表"""
    r_type = request.json.get('type', 'daily')
    try:
        if r_type == 'weekly':
            service.generate_weekly_report()
        else:
            service.generate_daily_report()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@report_bp.route('/download/<path:filename>', methods=['GET'])
def download(filename):
    """下载报表文件"""
    return send_from_directory(Config.REPORT_DIR, filename, as_attachment=True)