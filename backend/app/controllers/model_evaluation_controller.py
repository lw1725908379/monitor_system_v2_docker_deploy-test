from flask import Blueprint, jsonify, request
from backend.shared.database import DatabaseManager
from backend.app.core.config import Config

model_evaluation_bp = Blueprint('model_evaluation', __name__, url_prefix='/api/model_evaluation')
db = DatabaseManager(Config.DB_PATH)


@model_evaluation_bp.route('/summary', methods=['GET'])
def get_summary():
    """获取模型评估概览统计"""
    try:
        days = int(request.args.get('days', 30))
        summary = db.get_model_evaluation_summary(days)
        return jsonify({'success': True, 'data': summary})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@model_evaluation_bp.route('/trend', methods=['GET'])
def get_trend():
    """获取评估趋势数据（用于图表）"""
    try:
        days = int(request.args.get('days', 30))
        trend = db.get_model_evaluation_trend(days)
        return jsonify({'success': True, 'data': trend})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@model_evaluation_bp.route('/list', methods=['GET'])
def get_evaluations():
    """获取评估列表"""
    try:
        device_ip = request.args.get('device_ip')
        process_name = request.args.get('process_name')
        days = int(request.args.get('days', 30))
        evaluations = db.get_model_evaluations(device_ip, process_name, days)
        return jsonify({'success': True, 'data': evaluations})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@model_evaluation_bp.route('/process/<ip>/<path:process_name>', methods=['GET'])
def get_process_evaluation(ip, process_name):
    """获取特定进程的评估历史"""
    try:
        days = int(request.args.get('days', 30))
        evaluations = db.get_model_evaluations(device_ip=ip, process_name=process_name, days=days)
        return jsonify({'success': True, 'data': evaluations})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@model_evaluation_bp.route('/devices', methods=['GET'])
def get_by_device():
    """按设备汇总评估结果"""
    try:
        days = int(request.args.get('days', 30))
        evaluations = db.get_model_evaluations(days=days)

        # 按设备汇总
        device_summary = {}
        for ev in evaluations:
            ip = ev['device_ip']
            if ip not in device_summary:
                device_summary[ip] = {
                    'device_ip': ip,
                    'process_count': 0,
                    'avg_r2': [],
                    'avg_mae': [],
                    'good_count': 0
                }
            device_summary[ip]['process_count'] += 1
            if ev.get('r2_score'):
                device_summary[ip]['avg_r2'].append(ev['r2_score'])
            if ev.get('mae'):
                device_summary[ip]['avg_mae'].append(ev['mae'])
            if ev.get('r2_score', 0) >= 0.7:
                device_summary[ip]['good_count'] += 1

        # 计算平均值
        result = []
        for ip, data in device_summary.items():
            avg_r2 = sum(data['avg_r2']) / len(data['avg_r2']) if data['avg_r2'] else 0
            avg_mae = sum(data['avg_mae']) / len(data['avg_mae']) if data['avg_mae'] else 0
            result.append({
                'device_ip': ip,
                'process_count': data['process_count'],
                'avg_r2': round(avg_r2, 4),
                'avg_mae': round(avg_mae, 2),
                'good_count': data['good_count'],
                'good_rate': round(data['good_count'] / data['process_count'] * 100, 1) if data['process_count'] > 0 else 0
            })

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@model_evaluation_bp.route('/errors', methods=['GET'])
def get_prediction_errors():
    """获取预测误差记录"""
    try:
        device_ip = request.args.get('device_ip')
        process_name = request.args.get('process_name')
        days = int(request.args.get('days', 30))
        errors = db.get_prediction_errors(device_ip, process_name, days)
        return jsonify({'success': True, 'data': errors})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
