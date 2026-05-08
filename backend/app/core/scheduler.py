from apscheduler.schedulers.background import BackgroundScheduler
from backend.app.services.monitor_service import MonitorService
from backend.app.services.temperature_test_service import TemperatureTestService
from backend.app.services.memory_analysis_service import MemoryAnalysisService
from backend.app.services.device_service import DeviceService
from backend.app.utils.backup import run_backup
from backend.app.utils.storage_manager import run_storage_management
from backend.app.core.config import Config

scheduler = BackgroundScheduler()


def start_scheduler():
    if not scheduler.running:
        monitor_service = MonitorService()
        temp_test_service = TemperatureTestService()
        memory_analysis_service = MemoryAnalysisService()

        # 添加定时任务：每隔 X 秒检查所有设备
        scheduler.add_job(
            func=monitor_service.check_all_devices_async,
            trigger='interval',
            seconds=Config.MONITOR_CONFIG['check_interval'],
            id='global_monitor_job',
            replace_existing=True
        )

        # 添加定时任务：采集温度测试数据（与监控同步）
        scheduler.add_job(
            func=temp_test_service.collect_all_running_tests,
            trigger='interval',
            seconds=Config.MONITOR_CONFIG['check_interval'],
            id='temperature_test_job',
            replace_existing=True
        )

        # 添加定时任务：每天凌晨2点执行内存分析
        scheduler.add_job(
            func=memory_analysis_service.run_analysis,
            trigger='cron',
            hour=2,
            minute=0,
            id='memory_analysis_job',
            replace_existing=True
        )

        # 添加定时任务：每天凌晨3点自动备份
        scheduler.add_job(
            func=run_backup,
            trigger='cron',
            hour=3,
            minute=0,
            id='backup_job',
            replace_existing=True
        )

        # 添加定时任务：每天凌晨4点存储管理（清理日志、历史数据）
        scheduler.add_job(
            func=run_storage_management,
            trigger='cron',
            hour=4,
            minute=0,
            id='storage_management_job',
            replace_existing=True
        )

        # 添加定时任务：每天凌晨4点30分清理离线设备
        device_service = DeviceService()
        scheduler.add_job(
            func=device_service.cleanup_offline_devices,
            trigger='cron',
            hour=4,
            minute=30,
            id='cleanup_offline_devices_job',
            replace_existing=True
        )

        # 可以添加生成日报的任务 (cron) 先关闭，减少消耗
        # scheduler.add_job(..., trigger='cron', hour=23, ...)

        scheduler.start()
        print(">>> Scheduler Started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()