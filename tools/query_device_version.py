# -*- coding: utf-8 -*-
"""
项目设备软件版本查询工具
根据项目编号列表逐个查询设备软件版本信息
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import json
import time

# ==================== 配置区域 ====================
# 项目编号列表（手动填写）
PROJECT_CODES = [
    "p250795681",
    "p200899339",
    "p250681587",
    "p250682357",
    "p250696757",
    "p250682156",
    "p210635879",
    "p240974456",
    "p200622079",
    "p250581340",
    "p250782510",
    "p200420219",
    "p191015057",
    "p190610291",
    "p190191543",
    "p190991164",
    "p250883766",
    "p251200434"
]

# 产品型号
PRODUCT_CODE = "JSQ1609"

# 认证信息
COOKIE = "Admin-Token=eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMDUzNDIiLCJ1c2VySWQiOiIyMjQxYmI1Mjc3NzhlMGEwYjUzN2ZlYWY2MDBjODY2YiIsIm5hbWUiOiLpu4TotoUiLCJ1c2VyR3JvdXAiOiI4NTNlMzJhYzNhMjY3M2QyMzJhNDVmYjE0MjYxNzdiNCIsImV4cCI6MTc3ODMyOTkxM30.Slq2taBckIFNvhH4rZVzhjzU3cZZKU-wBdUveH0tkmlzfL14_tCmsDyADEZNX8daQK_PM4jDG6mUPYFYKhxaxUGcxrmeiJnY3Okq3ijkj-RKRXKig357vNzGAdaPlfPzqHOHuNcmdK2IzaHUb5jQXRYavIG-nGVWXTAuhAmBllQ; UserId=2241bb527778e0a0b537feaf600c866b; UserNo=105342"
X_TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMDUzNDIiLCJ1c2VySWQiOiIyMjQxYmI1Mjc3NzhlMGEwYjUzN2ZlYWY2MDBjODY2YiIsIm5hbWUiOiLpu4TotoUiLCJ1c2VyR3JvdXAiOiI4NTNlMzJhYzNhMjY3M2QyMzJhNDVmYjE0MjYxNzdiNCIsImV4cCI6MTc3ODMyOTkxM30.Slq2taBckIFNvhH4rZVzhjzU3cZZKU-wBdUveH0tkmlzfL14_tCmsDyADEZNX8daQK_PM4jDG6mUPYFYKhxaxUGcxrmeiJnY3Okq3ijkj-RKRXKig357vNzGAdaPlfPzqHOHuNcmdK2IzaHUb5jQXRYavIG-nGVWXTAuhAmBllQ"

# 超时时间（秒）
TIMEOUT = 60
# ================================================

API_URL = "https://jsrm.jslife.net/api/report/center/product/exportProductSoftVersionByCondition"


def query_device_version(item_code, session):
    """查询单个项目编号的设备版本信息"""
    print(f"\n[{item_code}] 查询中...")

    params = {
        "itemNameOrCode": item_code,
        "productNameOrCode": PRODUCT_CODE,
        "versionNum": "",
        "includeModule": "false",
        "startTimeStr": "",
        "endTimeStr": ""
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": COOKIE,
        "X-Token": X_TOKEN,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Origin": "https://jsrm.jslife.net",
        "Referer": "https://jsrm.jslife.net/"
    }

    try:
        response = session.post(API_URL, data=params, headers=headers, timeout=TIMEOUT)
        result = response.json()

        if result.get("success"):
            data = result.get("respData", [])
            print(f"[{item_code}] OK - {len(data)} 条记录")
            return data
        else:
            print(f"[{item_code}] FAIL - {result.get('message', '未知错误')}")
            return []

    except Exception as e:
        print(f"[{item_code}] ERROR - {e}")
        return []


def main():
    print("=" * 50)
    print("项目设备软件版本查询工具")
    print("=" * 50)
    print(f"项目数量: {len(PROJECT_CODES)}")
    print(f"产品型号: {PRODUCT_CODE}")
    print("=" * 50)

    session = requests.Session()
    all_results = []

    for i, code in enumerate(PROJECT_CODES):
        print(f"\n[{i+1}/{len(PROJECT_CODES)}]", end=" ")
        results = query_device_version(code, session)
        all_results.extend(results)

    # 汇总统计
    print("\n" + "=" * 50)
    print("查询结果汇总")
    print("=" * 50)

    project_stats = {}
    for item in all_results:
        item_code = item.get('itemCode', '未知')
        item_name = item.get('itemName', '未知')
        if item_code not in project_stats:
            project_stats[item_code] = {'name': item_name, 'count': 0, 'versions': set()}
        project_stats[item_code]['count'] += 1
        version = item.get('mainVersion', '未知')
        project_stats[item_code]['versions'].add(version)

    total_devices = 0
    for code, stats in project_stats.items():
        total_devices += stats['count']
        versions = ', '.join(stats['versions']) if stats['versions'] else '未知'
        print(f"{code} ({stats['name']}): {stats['count']} 台, 版本: {versions}")

    print(f"\n总计: {len(project_stats)} 个项目, {total_devices} 台设备")

    # 保存结果
    output_file = "device_version_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {output_file}")


if __name__ == "__main__":
    main()
