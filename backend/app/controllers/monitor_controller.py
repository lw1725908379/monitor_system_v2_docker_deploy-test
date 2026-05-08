from flask import Blueprint, jsonify, request
from backend.app.services.monitor_service import MonitorService
from backend.app.services.device_service import DeviceService

monitor_bp = Blueprint('monitor', __name__, url_prefix='/api/monitor')
monitor_service = MonitorService()
device_service = DeviceService()


@monitor_bp.route('/alerts/list', methods=['GET'])
def get_alert_list():
    """告警列表查询接口 (支持产品线筛选)"""
    try:
        from backend.app.repositories.device_repository import DeviceRepository
        repo = DeviceRepository()

        # 获取查询参数
        start = request.args.get('start')
        end = request.args.get('end')
        p_line = request.args.get('product_line') # 使用 product_line
        a_type = request.args.get('alert_type')
        ip = request.args.get('ip')

        # 如果只有日期没有时间，自动补全
        if start and len(start) == 10: start += ' 00:00:00'
        if end and len(end) == 10: end += ' 23:59:59'

        alerts = repo.db.query_alerts(start, end, p_line, a_type, ip)
        return jsonify({'success': True, 'data': alerts})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@monitor_bp.route('/alerts/options', methods=['GET'])
def get_alert_options():
    """获取筛选条件的下拉选项"""
    try:
        from backend.app.repositories.device_repository import DeviceRepository
        repo = DeviceRepository()

        # 获取所有产品线
        p_lines = repo.db.get_product_lines()
        # 获取所有告警类型
        a_types = repo.db.get_alert_types()

        return jsonify({
            'success': True,
            'product_lines': p_lines, # 【关键】Key名已修正
            'alert_types': a_types
        })
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@monitor_bp.route('/alerts/batch_delete', methods=['POST'])
def batch_delete_alerts():
    """批量删除告警"""
    try:
        from backend.app.repositories.device_repository import DeviceRepository
        repo = DeviceRepository()

        data = request.json or {}
        days = data.get('days')  # 删除多少天之前的告警，如7
        ip = data.get('ip')      # 删除指定IP的告警
        alert_type = data.get('alert_type')  # 删除指定类型的告警
        delete_all = data.get('delete_all', False)  # 删除所有告警

        repo.db.batch_delete_alerts(days=days, ip=ip, alert_type=alert_type, delete_all=delete_all)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@monitor_bp.route('/alerts/delete', methods=['POST'])
def delete_alerts_by_ids():
    """按ID删除告警"""
    try:
        from backend.app.repositories.device_repository import DeviceRepository
        repo = DeviceRepository()

        data = request.json or {}
        ids = data.get('ids', [])

        if not ids:
            return jsonify({'success': False, 'msg': '未选择告警'}), 400

        count = repo.db.delete_alerts_by_ids(ids)

        return jsonify({'success': True, 'deleted_count': count})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


# ==========================================
# 2. 看板与监控核心接口
# ==========================================

@monitor_bp.route('/data', methods=['GET'])
def get_dashboard_data():
    """前端轮询此接口获取所有设备数据"""
    try:
        data = device_service.get_all_devices_with_status()
        result = {d['ip']: d for d in data}
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@monitor_bp.route('/check_now', methods=['POST'])
def trigger_check():
    """立即检查"""
    try:
        ip = request.json.get('ip')
        if not ip: return jsonify({'success': False, 'msg': 'IP Required'}), 400

        # 异步检查
        import threading
        threading.Thread(target=monitor_service.check_single_device, args=(ip,)).start()

        return jsonify({'success': True, 'msg': 'Triggered'})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@monitor_bp.route('/device/<ip>', methods=['GET'])
def get_device_detail(ip):
    """项目详情查询 (含Top X进程融合逻辑)"""
    try:
        from backend.app.repositories.device_repository import DeviceRepository
        repo = DeviceRepository()

        device_info = repo.get_by_ip(ip)
        if not device_info:
            return jsonify({'error': '设备不存在'}), 404

        detail = repo.db.get_device_detail(ip)
        latest = repo.get_latest_record(ip)

        # 1. 获取所有已配置的风险进程（包括手动+自动从数据库保存的）
        all_risks = repo.get_custom_risk_processes(ip)

        # 2. 【数据融合逻辑】
        # 手动配置的和自动保存的进程都从数据库获取
        final_risk_list = []

        for item in all_risks:
            # 根据 source 字段标记类型
            if item.get('source') == 'auto':
                item['type'] = 'auto'
            else:
                item['type'] = 'manual'
            final_risk_list.append(item)

        status = latest.get('status', 'offline') if latest else 'offline'

        return jsonify({
            'device_info': device_info,
            'device_detail': detail,
            'latest_record': latest,
            'risk_processes': final_risk_list,
            'status': status
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500