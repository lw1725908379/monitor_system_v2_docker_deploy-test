#!/usr/bin/env python3
"""
数据备份脚本
功能：
1. 手动备份数据库
2. 导出CSV（ML友好）
3. 清理过期备份
"""

import os
import sqlite3
import zipfile
import shutil
import csv
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# 配置 - 容器内运行用 /app/storage，开发用相对路径
import sys

# 检测是否在Docker容器中运行
if os.path.exists('/app'):
    # Docker容器内
    BASE_DIR = '/app'
else:
    # 本地开发
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

STORAGE_DIR = os.path.join(BASE_DIR, 'storage')
BACKUP_DIR = os.path.join(STORAGE_DIR, 'backups')
EXPORTS_DIR = os.path.join(STORAGE_DIR, 'exports')
DB_PATH = os.path.join(STORAGE_DIR, 'devices.db')

# 保留天数
RETENTION_DAYS = 30


def ensure_dirs():
    """确保目录存在"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(EXPORTS_DIR, exist_ok=True)


def backup_database():
    """备份SQLite数据库"""
    if not os.path.exists(DB_PATH):
        logger.warning(f"数据库文件不存在: {DB_PATH}")
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"devices_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    try:
        # 使用副本备份，避免锁问题
        shutil.copy2(DB_PATH, backup_path)
        logger.info(f"数据库备份完成: {backup_name}")
        return backup_name
    except Exception as e:
        logger.error(f"数据库备份失败: {e}")
        return None


def export_table_to_csv(cursor, table_name, csv_path, columns=None):
    """导出单个表到CSV"""
    try:
        # 获取列名
        if columns is None:
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]

        # 查询数据
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()

        # 写入CSV
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(columns)  # 写入表头
            writer.writerows(rows)   # 写入数据

        logger.info(f"导出 {table_name}: {len(rows)} 行")
        return len(rows)
    except Exception as e:
        logger.warning(f"导出 {table_name} 失败: {e}")
        return 0


def export_csv():
    """导出数据为CSV格式（机器学习友好）"""
    if not os.path.exists(DB_PATH):
        logger.warning(f"数据库文件不存在: {DB_PATH}")
        return []

    exported_files = []
    timestamp = datetime.now().strftime('%Y%m%d')

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 1. 导出监控历史（限制最近100万行，避免过大）
        csv_path = os.path.join(EXPORTS_DIR, f'monitoring_history_{timestamp}.csv')
        count = export_table_to_csv(cursor, 'monitoring_history', csv_path)
        if count > 0:
            exported_files.append(csv_path)

        # 2. 导出设备信息
        csv_path = os.path.join(EXPORTS_DIR, f'devices_{timestamp}.csv')
        count = export_table_to_csv(cursor, 'devices', csv_path)
        if count > 0:
            exported_files.append(csv_path)

        # 3. 导出告警记录（限制最近10000条）
        cursor.execute("SELECT * FROM alerts ORDER BY created_at DESC LIMIT 10000")
        rows = cursor.fetchall()
        cursor.execute("PRAGMA table_info(alerts)")
        columns = [row[1] for row in cursor.fetchall()]
        csv_path = os.path.join(EXPORTS_DIR, f'alerts_{timestamp}.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)
        exported_files.append(csv_path)
        logger.info(f"导出 alerts: {len(rows)} 行")

        # 4. 导出Core文件记录
        csv_path = os.path.join(EXPORTS_DIR, f'core_files_{timestamp}.csv')
        count = export_table_to_csv(cursor, 'core_files', csv_path)
        if count > 0:
            exported_files.append(csv_path)

        # 5. 导出设备详情
        csv_path = os.path.join(EXPORTS_DIR, f'device_details_{timestamp}.csv')
        count = export_table_to_csv(cursor, 'device_details', csv_path)
        if count > 0:
            exported_files.append(csv_path)

        conn.close()
        return exported_files

    except Exception as e:
        logger.error(f"CSV导出失败: {e}")
        return []


def create_zip_backup(backup_name, exported_files):
    """创建压缩包（包含数据库备份 + CSV导出）"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_name = f"monitor_backup_{timestamp}.zip"
    zip_path = os.path.join(BACKUP_DIR, zip_name)

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 添加数据库备份
            db_backup = os.path.join(BACKUP_DIR, backup_name)
            if os.path.exists(db_backup):
                zf.write(db_backup, backup_name)

            # 添加CSV导出
            for csv_file in exported_files:
                if os.path.exists(csv_file):
                    zf.write(csv_file, os.path.basename(csv_file))

        logger.info(f"压缩包创建完成: {zip_name}")
        return zip_name
    except Exception as e:
        logger.error(f"压缩包创建失败: {e}")
        return None


def cleanup_old_backups():
    """清理过期备份"""
    if not os.path.exists(BACKUP_DIR):
        return

    now = datetime.now().timestamp()
    cleaned = 0

    for filename in os.listdir(BACKUP_DIR):
        filepath = os.path.join(BACKUP_DIR, filename)
        if os.path.isfile(filepath):
            # 检查文件修改时间
            mtime = os.path.getmtime(filepath)
            age_days = (now - mtime) / 86400

            if age_days > RETENTION_DAYS:
                try:
                    os.remove(filepath)
                    cleaned += 1
                    logger.info(f"清理过期备份: {filename}")
                except Exception as e:
                    logger.warning(f"清理失败: {filename}, {e}")

    if cleaned > 0:
        logger.info(f"共清理 {cleaned} 个过期文件")


def run_backup():
    """执行完整备份流程"""
    logger.info("=" * 50)
    logger.info("开始备份任务")
    logger.info("=" * 50)

    ensure_dirs()

    # 1. 备份数据库
    backup_name = backup_database()
    if not backup_name:
        logger.error("备份失败，终止任务")
        return False

    # 2. 导出CSV
    exported_files = export_csv()

    # 3. 创建压缩包
    if exported_files:
        zip_name = create_zip_backup(backup_name, exported_files)

    # 4. 清理过期文件
    cleanup_old_backups()

    logger.info("=" * 50)
    logger.info("备份任务完成")
    logger.info("=" * 50)

    return True


def get_backup_list():
    """获取备份文件列表"""
    if not os.path.exists(BACKUP_DIR):
        return []

    files = []
    for filename in os.listdir(BACKUP_DIR):
        filepath = os.path.join(BACKUP_DIR, filename)
        if os.path.isfile(filepath):
            stat = os.stat(filepath)
            files.append({
                'name': filename,
                'size': stat.st_size,
                'mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })

    # 按时间倒序
    files.sort(key=lambda x: x['mtime'], reverse=True)
    return files


if __name__ == '__main__':
    run_backup()
