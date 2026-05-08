import sys
import os
import argparse

current_script_path = os.path.abspath(__file__)
backend_dir = os.path.dirname(current_script_path)
project_root = os.path.dirname(backend_dir)

sys.path.insert(0, project_root)

from backend.app import create_app
from waitress import serve

app = create_app()

if __name__ == '__main__':
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='设备监控系统')
    parser.add_argument('--port', type=int, default=8888, help='服务端口号 (默认: 8888)')
    args = parser.parse_args()

    # 尝试从 port.txt 读取端口配置
    port_file = os.path.join(backend_dir, 'port.txt')
    if os.path.exists(port_file):
        try:
            with open(port_file, 'r') as f:
                port = int(f.read().strip())
        except:
            port = args.port
    else:
        port = args.port

    print(f"Project Root added to path: {project_root}")
    print("Starting Monitor System (Windows Native Mode)...")
    print(f"API available at http://localhost:{port}/api/...")
    print(f"Web UI available at http://localhost:{port}/")
    serve(app, host='0.0.0.0', port=port, threads=10)
