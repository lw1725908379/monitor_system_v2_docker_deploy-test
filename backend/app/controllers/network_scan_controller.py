from flask import Blueprint, jsonify, request
import threading
import time
from backend.app.services.network_scan_service import NetworkScanService
from backend.app.services.device_service import DeviceService

scan_bp = Blueprint('scan', __name__, url_prefix='/api/scan')
scan_service = NetworkScanService()
device_service = DeviceService()

# 异步任务存储
_scan_tasks = {}  # {task_id: {'status': 'running'|'completed', 'devices': [], 'start_time': timestamp}}
_task_lock = threading.Lock()


def _run_scan_task(task_id, subnet, start_ip, end_ip):
    """后台扫描任务"""
    try:
        devices = scan_service.scan_network(subnet, start_ip, end_ip)

        # 自动添加发现的设备到监控
        added_count = 0
        for device in devices:
            ip = device.get('ip')
            if ip and not device_service.repo.device_exists(ip):
                device_service.repo.add_device(
                    ip,
                    '其他',  # 默认产品线
                    'root',
                    'Jsst_168'
                )
                added_count += 1
                time.sleep(0.1)  # 避免并发过高

        with _task_lock:
            _scan_tasks[task_id] = {
                'status': 'completed',
                'devices': devices,
                'added_count': added_count,
                'end_time': time.time()
            }
    except Exception as e:
        with _task_lock:
            _scan_tasks[task_id] = {
                'status': 'failed',
                'error': str(e),
                'end_time': time.time()
            }


@scan_bp.route('/network', methods=['POST'])
def start_scan():
    """启动异步扫描"""
    try:
        data = request.json
        subnet = data.get('subnet', '').strip()
        start_ip = data.get('start_ip', 1)
        end_ip = data.get('end_ip', 254)

        # 参数验证
        if not subnet:
            return jsonify({'success': False, 'msg': '请输入网段'}), 400

        parts = subnet.split('.')
        if len(parts) != 3:
            return jsonify({'success': False, 'msg': '网段格式错误'}), 400

        try:
            start_ip = int(start_ip)
            end_ip = int(end_ip)
            if start_ip < 1 or end_ip > 254 or start_ip > end_ip:
                return jsonify({'success': False, 'msg': 'IP范围错误'}), 400
        except ValueError:
            return jsonify({'success': False, 'msg': 'IP范围必须为数字'}), 400

        # 先检查已监控设备
        all_devices = device_service.get_all_devices_with_status()
        matching_devices = []
        for device_data in all_devices:
            ip = device_data.get('ip', '')
            ip_parts = ip.split('.')
            if len(ip_parts) == 4:
                ip_prefix = '.'.join(ip_parts[:3])
                ip_last = int(ip_parts[3])
                if ip_prefix == subnet and start_ip <= ip_last <= end_ip:
                    matching_devices.append({'ip': ip, 'online': True, 'is_jieshun': True})

        if matching_devices:
            return jsonify({
                'success': True,
                'devices': matching_devices,
                'count': len(matching_devices),
                'source': 'monitored'
            })

        # 启动后台扫描任务
        task_id = f"{subnet}_{start_ip}_{end_ip}_{int(time.time())}"
        with _task_lock:
            _scan_tasks[task_id] = {
                'status': 'running',
                'subnet': subnet,
                'start_time': time.time()
            }

        # 启动后台线程
        thread = threading.Thread(target=_run_scan_task, args=(task_id, subnet, start_ip, end_ip))
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '后台扫描已启动，请稍候查看结果'
        })

    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@scan_bp.route('/task/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """查询扫描任务状态"""
    with _task_lock:
        task = _scan_tasks.get(task_id)

    if not task:
        return jsonify({'success': False, 'msg': '任务不存在'}), 404

    if task['status'] == 'running':
        return jsonify({
            'success': True,
            'status': 'running',
            'elapsed': time.time() - task['start_time']
        })

    if task['status'] == 'completed':
        return jsonify({
            'success': True,
            'status': 'completed',
            'devices': task['devices'],
            'added_count': task.get('added_count', 0)
        })

    return jsonify({
        'success': False,
        'status': 'failed',
        'error': task.get('error', '未知错误')
    })
