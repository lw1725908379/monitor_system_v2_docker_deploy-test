from flask import Blueprint, jsonify, request
from backend.app.services.memory_analysis_service import MemoryAnalysisService
from datetime import datetime

memory_analysis_bp = Blueprint('memory_analysis', __name__, url_prefix='/api/memory_analysis')
memory_analysis_service = MemoryAnalysisService()


@memory_analysis_bp.route('/run', methods=['POST'])
def run_analysis():
    """手动触发内存分析"""
    try:
        days = request.json.get('days', 7) if request.json else 7
        service = MemoryAnalysisService(days=days)
        result = service.run_analysis()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@memory_analysis_bp.route('/results', methods=['GET'])
def get_results():
    """获取分析结果"""
    try:
        device_ip = request.args.get('device_ip')
        days = int(request.args.get('days', 30))

        from backend.shared.database import DatabaseManager
        from backend.app.core.config import Config
        db = DatabaseManager(Config.DB_PATH)
        results = db.get_memory_analysis_results(device_ip, days)

        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@memory_analysis_bp.route('/latest_log', methods=['GET'])
def get_latest_log():
    """获取最近的分析日志"""
    try:
        from backend.shared.database import DatabaseManager
        from backend.app.core.config import Config
        db = DatabaseManager(Config.DB_PATH)
        log = db.get_latest_analysis_log()
        return jsonify({'success': True, 'data': log})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@memory_analysis_bp.route('/delete/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    """删除单条内存分析记录"""
    try:
        from backend.shared.database import DatabaseManager
        from backend.app.core.config import Config
        db = DatabaseManager(Config.DB_PATH)
        db.delete_memory_analysis(record_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@memory_analysis_bp.route('/clear', methods=['POST'])
def clear_records():
    """清空所有内存分析记录"""
    try:
        from backend.shared.database import DatabaseManager
        from backend.app.core.config import Config
        db = DatabaseManager(Config.DB_PATH)
        device_ip = request.json.get('device_ip') if request.json else None
        db.delete_all_memory_analysis(device_ip)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
