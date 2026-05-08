from flask import Blueprint, jsonify, request
from backend.app.services.device_service import DeviceService
from backend.app.repositories.device_repository import DeviceRepository

device_bp = Blueprint('device', __name__, url_prefix='/api/device')
service = DeviceService()
repo = DeviceRepository()

@device_bp.route('/add', methods=['POST'])
def add_device():
    try:
        if service.add_device(request.json):
            return jsonify({'success': True})
        return jsonify({'success': False, 'msg': '设备已存在或添加失败'}), 400
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500

@device_bp.route('/delete/<ip>', methods=['DELETE'])
def delete_device(ip):
    if service.delete_device(ip):
        return jsonify({'success': True})
    return jsonify({'success': False}), 400

@device_bp.route('/batch_delete', methods=['POST'])
def batch_delete_devices():
    """批量删除设备"""
    try:
        ips = request.json.get('ips', [])
        if not ips:
            return jsonify({'success': False, 'msg': '未选择设备'}), 400

        count = repo.batch_delete_devices(ips)
        return jsonify({'success': True, 'deleted_count': count})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500

@device_bp.route('/update', methods=['PUT'])
def update_device():
    """修改单个设备信息"""
    try:
        data = request.json
        ip = data.get('ip')
        if not ip:
            return jsonify({'success': False, 'msg': '缺少IP地址'}), 400

        if repo.update_device(
            ip,
            product_line=data.get('product_line'),
            username=data.get('username'),
            password=data.get('password')
        ):
            return jsonify({'success': True})
        return jsonify({'success': False, 'msg': '更新失败'}), 400
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500

@device_bp.route('/batch_update', methods=['POST'])
def batch_update_device():
    """批量修改设备产品线"""
    try:
        data = request.json
        ips = data.get('ips', [])
        product_line = data.get('product_line')

        if not ips:
            return jsonify({'success': False, 'msg': '请选择要修改的设备'}), 400
        if not product_line:
            return jsonify({'success': False, 'msg': '请选择产品线'}), 400

        if repo.batch_update_product_line(ips, product_line):
            return jsonify({'success': True, 'count': len(ips)})
        return jsonify({'success': False, 'msg': '批量更新失败'}), 400
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@device_bp.route('/risk_process/add', methods=['POST'])
def add_risk():
    data = request.json
    try:
        # 如果没有提供pid，则自动获取当前进程的PID
        pid = data.get('pid')
        if not pid:
            # 需要连接设备获取当前PID
            from backend.app.core.ssh_client import SSHClient
            from backend.app.repositories.device_repository import DeviceRepository
            repo = DeviceRepository()
            device = repo.get_by_ip(data['ip'])
            if device:
                ssh = SSHClient(data['ip'], device['username'], device['password'])
                if ssh.connect():
                    # 获取进程PID
                    cmd = f"pidof {data['process_name']}"
                    pid_output = ssh.execute_cmd(cmd)
                    if not pid_output:
                        cmd = f"ps | grep '{data['process_name']}' | grep -v grep | awk '{{print $1}}'"
                        pid_output = ssh.execute_cmd(cmd)
                    if pid_output and pid_output.strip():
                        pid = pid_output.strip().split()[0]
                    ssh.close()

        repo.add_risk_process_config(
            data['ip'],
            pid,
            data['process_name'],
            int(data['allocated_memory'])
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500

@device_bp.route('/risk_process/delete/<int:id>', methods=['DELETE'])
def del_risk(id):
    if repo.delete_risk_process_config(id):
        return jsonify({'success': True})
    return jsonify({'success': False}), 400