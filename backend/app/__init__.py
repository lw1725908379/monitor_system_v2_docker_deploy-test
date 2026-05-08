import os
from flask import Flask, send_from_directory
from backend.app.controllers.monitor_controller import monitor_bp
from backend.app.controllers.device_controller import device_bp
from backend.app.controllers.network_scan_controller import scan_bp
from backend.app.core.scheduler import start_scheduler
from backend.shared.database import DatabaseManager
from backend.app.core.config import Config
from backend.app.controllers.report_controller import report_bp
from backend.app.controllers.temperature_test_controller import temp_test_bp
from backend.app.controllers.memory_analysis_controller import memory_analysis_bp
from backend.app.controllers.backup_controller import backup_bp


def create_app():
    # 获取项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(current_dir)
    project_root = os.path.dirname(backend_dir)
    frontend_dir = os.path.join(project_root, 'frontend')

    app = Flask(__name__, static_folder=None)

    # 配置静态文件服务
    @app.route('/')
    def index():
        return send_from_directory(frontend_dir, 'index.html')

    @app.route('/<path:filename>')
    def serve_static(filename):
        return send_from_directory(frontend_dir, filename)

    # 1. 初始化数据库
    db = DatabaseManager(Config.DB_PATH)

    # 2. 注册路由 (Controller)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(device_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(temp_test_bp)
    app.register_blueprint(memory_analysis_bp)
    app.register_blueprint(backup_bp)

    # 3. 启动调度器
    start_scheduler()

    return app
