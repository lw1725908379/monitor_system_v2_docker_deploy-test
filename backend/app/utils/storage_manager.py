#!/usr/bin/env python3
"""
存储空间管理器
功能：
1. 日志清理（保留7天）
2. 监控历史数据归档/清理
3. 临时文件清理
4. 数据库优化（VACUUM）
"""

import os
import sqlite3
import time
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# 配置 - 容器内运行用 /app/storage，开发用相对路径
# 检测是否在Docker容器中运行
if os.path.exists('/app'):
    # Docker容器内
    BASE_DIR = '/app'
else:
    # 本地开发
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

STORAGE_DIR = os.path.join(BASE_DIR, 'storage')

# 保留天数
LOG_RETENTION_DAYS = 7
HISTORY_RETENTION_DAYS = 90  # 监控历史保留90天
REPORT_RETENTION_DAYS = 30   # 日报表保留30天


def get_dir_size(path):
    """获取目录大小（MB）"""
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)
    except Exception:
        pass
    return total / (1024 * 1024)


def cleanup_logs():
    """清理过期日志文件"""
    log_dir = os.path.join(BASE_DIR, 'logs')
    if not os.path.exists(log_dir):
        return 0

    now = time.time()
    cutoff = now - (LOG_RETENTION_DAYS * 86400)
    cleaned = 0

    for filename in os.listdir(log_dir):
        filepath = os.path.join(log_dir, filename)
        if os.path.isfile(filepath):
            # 检查修改时间
            if os.path.getmtime(filepath) < cutoff:
                try:
                    os.remove(filepath)
                    cleaned += 1
                    logger.info(f"清理日志: {filename}")
                except Exception as e:
                    logger.warning(f"清理失败: {filename}, {e}")

    return cleaned


def cleanup_reports():
    """清理过期日报表"""
    reports_dir = os.path.join(STORAGE_DIR, 'reports')
    if not os.path.exists(reports_dir):
        return 0

    now = time.time()
    cutoff = now - (REPORT_RETENTION_DAYS * 86400)
    cleaned = 0

    for filename in os.listdir(reports_dir):
        filepath = os.path.join(reports_dir, filename)
        if os.path.isfile(filepath):
            if os.path.getmtime(filepath) < cutoff:
                try:
                    os.remove(filepath)
                    cleaned += 1
                    logger.info(f"清理报表: {filename}")
                except Exception:
                    pass

    return cleaned


def cleanup_monitoring_history():
    """清理过期的监控历史数据"""
    db_path = os.path.join(STORAGE_DIR, 'devices.db')
    if not os.path.exists(db_path):
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 计算截止时间
        cutoff_date = datetime.now() - timedelta(days=HISTORY_RETENTION_DAYS)
        cutoff_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')

        # 删除过期数据
        cursor.execute("DELETE FROM monitoring_history WHERE check_time < ?", (cutoff_str,))
        deleted = cursor.rowcount

        if deleted > 0:
            conn.commit()
            logger.info(f"清理监控历史: {deleted} 条记录")

            # 执行VACUUM优化数据库
            cursor.execute("VACUUM")
            logger.info("数据库 VACUUM 完成")

        conn.close()
        return deleted

    except Exception as e:
        logger.error(f"清理监控历史失败: {e}")
        conn.close()
        return 0


def cleanup_temp_files():
    """清理临时文件"""
    temp_patterns = ['.tmp', '.temp', '~']
    cleaned = 0

    for root, dirs, files in os.walk(STORAGE_DIR):
        # 跳过重要目录
        if 'backups' in root or 'exports' in root:
            continue

        for f in files:
            if any(f.endswith(p) for p in temp_patterns):
                try:
                    os.remove(os.path.join(root, f))
                    cleaned += 1
                except Exception:
                    pass

    return cleaned


def get_storage_stats():
    """获取存储统计"""
    stats = {
        'database': 0,
        'backups': 0,
        'exports': 0,
        'reports': 0,
        'logs': 0,
        'total': 0
    }

    # 数据库
    db_path = os.path.join(STORAGE_DIR, 'devices.db')
    if os.path.exists(db_path):
        stats['database'] = os.path.getsize(db_path) / (1024 * 1024)

    # 备份
    backups_dir = os.path.join(STORAGE_DIR, 'backups')
    if os.path.exists(backups_dir):
        stats['backups'] = get_dir_size(backups_dir)

    # 导出
    exports_dir = os.path.join(STORAGE_DIR, 'exports')
    if os.path.exists(exports_dir):
        stats['exports'] = get_dir_size(exports_dir)

    # 报表
    reports_dir = os.path.join(STORAGE_DIR, 'reports')
    if os.path.exists(reports_dir):
        stats['reports'] = get_dir_size(reports_dir)

    # 日志
    logs_dir = os.path.join(BASE_DIR, 'logs')
    if os.path.exists(logs_dir):
        stats['logs'] = get_dir_size(logs_dir)

    stats['total'] = sum(stats.values())
    return stats


def run_storage_management():
    """执行存储管理"""
    logger.info("=" * 50)
    logger.info("开始存储管理任务")
    logger.info("=" * 50)

    # 1. 获取清理前统计
    stats_before = get_storage_stats()
    logger.info(f"清理前存储: {stats_before['total']:.2f} MB")

    # 2. 清理日志
    log_count = cleanup_logs()
    logger.info(f"清理日志文件: {log_count} 个")

    # 3. 清理报表
    report_count = cleanup_reports()
    logger.info(f"清理过期报表: {report_count} 个")

    # 4. 清理监控历史
    history_count = cleanup_monitoring_history()
    logger.info(f"清理监控历史: {history_count} 条")

    # 5. 清理临时文件
    temp_count = cleanup_temp_files()
    logger.info(f"清理临时文件: {temp_count} 个")

    # 6. 获取清理后统计
    stats_after = get_storage_stats()
    saved = stats_before['total'] - stats_after['total']
    logger.info(f"清理后存储: {stats_after['total']:.2f} MB")
    logger.info(f"释放空间: {saved:.2f} MB")

    logger.info("=" * 50)
    logger.info("存储管理任务完成")
    logger.info("=" * 50)

    return {
        'log_count': log_count,
        'report_count': report_count,
        'history_count': history_count,
        'temp_count': temp_count,
        'saved_mb': saved
    }


if __name__ == '__main__':
    run_storage_management()
