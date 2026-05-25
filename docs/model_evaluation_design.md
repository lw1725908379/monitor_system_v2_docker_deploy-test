# 模型评估优化设计方案

> 创建日期: 2026-05-25
> 版本: 1.0

---

## 一、背景

现有内存分析服务中的 Ridge 回归模型缺乏量化评估机制，无法验证模型有效性。

**当前问题：**
- 无数据集划分，直接使用全部数据训练
- 无评估指标（MAE/RMSE/R²/MAPE）
- 无误差监控
- 无历史追溯

---

## 二、量化指标设计

### 2.1 评估指标定义

| 指标 | 公式 | 含义 | 优良标准 |
|------|------|------|----------|
| **R² (决定系数)** | 1 - Σ(y-ŷ)² / Σ(y-ȳ)² | 模型解释力 | > 0.7 良好<br>> 0.9 优秀 |
| **MAE** | mean(\|y - ŷ\|) | 平均绝对误差(MB) | 越小越好 |
| **RMSE** | √mean((y-ŷ)²) | 对大误差更敏感 | 越小越好 |
| **MAPE** | mean(\|y-ŷ\|/y) × 100% | 相对误差(%) | < 10% 良好<br>< 20% 可接受 |
| **MaxAE** | max(\|y - ŷ\|) | 最大绝对误差 | 越小越好 |

### 2.2 趋势预测准确度

| 指标 | 公式 | 含义 |
|------|------|------|
| **趋势准确率** | 预测趋势 == 实际趋势的比例 | 判断增长/下降/稳定是否正确 |
| **方向准确率** | 预测方向(升/降) == 实际方向的比例 | 判断走向是否正确 |

---

## 三、数据库设计

### 3.1 模型评估记录表

```sql
CREATE TABLE IF NOT EXISTS model_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_ip TEXT NOT NULL,
    process_name TEXT NOT NULL,
    evaluation_date TEXT NOT NULL,
    data_points INTEGER NOT NULL,
    train_size INTEGER NOT NULL,
    test_size INTEGER NOT NULL,
    
    -- 评估指标
    r2_score REAL,
    mae REAL,
    rmse REAL,
    mape REAL,
    max_ae REAL,
    
    -- 趋势预测
    predicted_trend TEXT,
    actual_trend TEXT,
    trend_correct BOOLEAN,
    
    -- 预测结果
    recommended_memory INTEGER,
    predicted_max REAL,
    actual_max REAL,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(device_ip, process_name, evaluation_date)
);
```

### 3.2 预测误差记录表

```sql
CREATE TABLE IF NOT EXISTS prediction_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_ip TEXT NOT NULL,
    process_name TEXT NOT NULL,
    prediction_date TEXT NOT NULL,
    check_date TEXT NOT NULL,
    predicted_value REAL NOT NULL,
    actual_value REAL NOT NULL,
    error_pct REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 四、评估流程

```
┌──────────────────────────────────────────────────────────┐
│                   完整预测+评估流程                      │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  1. 数据准备 (60个点)                                   │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  2. 特征工程 → X(60×5), y(60)                         │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  3. 数据划分: train(80%) / test(20%)                  │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  4. 训练模型: Ridge.fit(X_train, y_train)              │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  5. 测试集预测: y_pred = model.predict(X_test)         │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  6. 计算指标: MAE, RMSE, R², MAPE                      │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  7. 全量训练: 用全部数据重新训练模型                    │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  8. 预测未来: 120步                                    │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  9. 保存评估结果到数据库                                │
└──────────────────────────────────────────────────────────┘
```

---

## 五、可视化设计

### 5.1 评估概览页面

- 关键指标卡片：R² 均值、MAE 均值、MAPE 均值、趋势准确率
- R² 趋势折线图
- 进程评估列表表格
- 评估分布饼图（良好/一般/较差）

### 5.2 进程详情页面

- 评估指标详情
- 预测 vs 实际对比折线图
- 评估历史表格

---

## 六、API 设计

| 接口 | 说明 |
|------|------|
| `GET /api/model-evaluation/summary` | 获取评估概览统计 |
| `GET /api/model-evaluation/trend` | 获取评估趋势数据(图表用) |
| `GET /api/model-evaluation/process/{ip}/{process}` | 获取特定进程的评估历史 |
| `GET /api/model-evaluation/devices` | 按设备汇总评估结果 |

---

## 七、配置项

```python
ML_MODEL_CONFIG = {
    # 现有配置
    'ridge_alpha': 1.0,
    'analysis_days': 7,
    'prediction_steps': 120,
    'min_data_points': 50,
    'safety_margin': {...},
    'trend_threshold': {...},
    
    # 新增配置
    'test_size_ratio': 0.2,        # 测试集比例
    'enable_evaluation': True,      # 是否启用评估
}
```

---

## 八、涉及修改的文件

| 文件 | 修改内容 |
|------|----------|
| `backend/app/core/config.py` | 新增评估配置项 |
| `backend/shared/database.py` | 新增评估表和方法 |
| `backend/app/services/memory_analysis_service.py` | 添加评估逻辑 |
| `backend/app/controllers/model_evaluation_controller.py` | 新增评估API |
| `frontend/model_evaluation.html` | 新增评估页面 |

---

## 九、预期效果

1. **量化透明** - 每次分析都有明确的 R²/MAE/MAPE 指标
2. **历史可查** - 评估结果持久化到数据库，可追溯历史
3. **趋势可见** - 图表展示指标变化趋势
4. **问题定位** - 通过列表快速定位低质量模型
5. **持续监控** - R² 下降或 MAPE 上升时告警
