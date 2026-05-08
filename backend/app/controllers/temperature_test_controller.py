from flask import Blueprint, jsonify, request
from backend.app.services.temperature_test_service import TemperatureTestService

temp_test_bp = Blueprint('temperature_test', __name__, url_prefix='/api/temperature_test')
temp_test_service = TemperatureTestService()


@temp_test_bp.route('/start', methods=['POST'])
def start_test():
    """启动温度测试"""
    try:
        data = request.json
        device_ip = data.get('device_ip')
        test_phase = data.get('test_phase')  # 'baseline', 'high', 'low'
        test_duration = data.get('test_duration')  # 分钟
        threshold_memory_pct = data.get('threshold_memory_pct', 10)  # 默认10%
        threshold_temp_pct = data.get('threshold_temp_pct', 10)  # 默认10%
        baseline_id = data.get('baseline_id')

        if not device_ip or not test_phase:
            return jsonify({'success': False, 'msg': '缺少必要参数'}), 400

        test_id = temp_test_service.start_test(
            device_ip, test_phase, test_duration,
            threshold_memory_pct, threshold_temp_pct, baseline_id
        )

        return jsonify({'success': True, 'test_id': test_id})
    except ValueError as e:
        return jsonify({'success': False, 'msg': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@temp_test_bp.route('/stop', methods=['POST'])
def stop_test():
    """停止温度测试"""
    try:
        data = request.json
        test_id = data.get('test_id')

        if not test_id:
            return jsonify({'success': False, 'msg': '缺少测试ID'}), 400

        temp_test_service.stop_test(test_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@temp_test_bp.route('/list', methods=['GET'])
def list_tests():
    """获取测试列表"""
    try:
        device_ip = request.args.get('device_ip')
        status = request.args.get('status')

        tests = temp_test_service.get_tests(device_ip, status)
        return jsonify({'success': True, 'data': tests})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@temp_test_bp.route('/detail/<int:test_id>', methods=['GET'])
def get_test_detail(test_id):
    """获取测试详情"""
    try:
        test = temp_test_service.get_test(test_id)
        if not test:
            return jsonify({'success': False, 'msg': '测试不存在'}), 404
        return jsonify({'success': True, 'data': test})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@temp_test_bp.route('/baselines', methods=['GET'])
def get_baselines():
    """获取常温基准测试列表"""
    try:
        device_ip = request.args.get('device_ip')
        if not device_ip:
            return jsonify({'success': False, 'msg': '缺少设备IP'}), 400

        baselines = temp_test_service.get_baseline_tests(device_ip)
        return jsonify({'success': True, 'data': baselines})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500


@temp_test_bp.route('/delete/<int:test_id>', methods=['DELETE'])
def delete_test(test_id):
    """删除温度测试记录"""
    try:
        temp_test_service.delete_test(test_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500
