from flask import Blueprint, jsonify, send_file
import threading
from backend.app.utils.backup import run_backup, get_backup_list

backup_bp = Blueprint('backup', __name__, url_prefix='/api/backup')


@backup_bp.route('/run', methods=['POST'])
def start_backup():
    """手动触发备份"""
    try:
        # 后台执行备份
        thread = threading.Thread(target=run_backup)
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'msg': '备份任务已启动，请稍候查看结果'
        })
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@backup_bp.route('/list', methods=['GET'])
def list_backups():
    """获取备份文件列表"""
    try:
        files = get_backup_list()
        return jsonify({
            'success': True,
            'files': files
        })
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@backup_bp.route('/download/<filename>', methods=['GET'])
def download_backup(filename):
    """下载备份文件"""
    try:
        import os
        from flask import current_app

        # 安全检查
        filename = filename.replace('..', '').replace('/', '')

        # 构建文件路径
        storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'storage')
        backup_dir = os.path.join(storage_dir, 'backups')
        filepath = os.path.join(backup_dir, filename)

        if not os.path.exists(filepath):
            return jsonify({'success': False, 'msg': '文件不存在'}), 404

        return send_file(filepath, as_attachment=True)
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500
