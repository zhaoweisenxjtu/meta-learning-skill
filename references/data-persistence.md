# 学习数据持久化

学习进度、复习历史、评估结果以 JSON 格式存储在用户本地。本文档定义数据格式和操作协议。

## 存储位置

默认数据目录：`~/.meta-learning/`

```
~/.meta-learning/
├── sm2-data.json         # SM-2 间隔重复排期数据
├── assessment-log.json   # 评估历史记录
├── learning-journal.json # 学习日志（每日记录）
└── config.json           # 用户偏好配置
```

## SM-2 排期数据格式

文件：`~/.meta-learning/sm2-data.json`

```json
{
  "<topic-slug>": {
    "topic": "贝叶斯定理",
    "ef": 2.5,
    "interval": 6,
    "repetitions": 3,
    "next_review": "2026-06-16",
    "history": [
      {"date": "2026-06-10", "quality": 4},
      {"date": "2026-06-12", "quality": 5}
    ]
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `topic` | string | 主题名称 |
| `ef` | float | 难易度因子，≥1.3，初始2.5 |
| `interval` | int | 当前复习间隔（天） |
| `repetitions` | int | 连续评分≥3的次数 |
| `next_review` | string | 下次复习日期 (YYYY-MM-DD) |
| `history` | array | 每次评分的记录 |

## 评估历史格式

文件：`~/.meta-learning/assessment-log.json`

```json
{
  "entries": [
    {
      "date": "2026-06-10",
      "topic": "线性代数",
      "level_before": 2,
      "level_after": 3,
      "method": "费曼+主动回忆",
      "duration_minutes": 45,
      "notes": "特征值概念已掌握，特征向量应用还需练习"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `date` | string | 评估日期 |
| `topic` | string | 评估主题 |
| `level_before` | int | 评估前层级 (1-5) |
| `level_after` | int | 评估后层级 (1-5) |
| `method` | string | 使用的方法组合 |
| `duration_minutes` | int | 投入时间（分钟） |
| `notes` | string | 自由文本备注 |

## 学习日志格式

文件：`~/.meta-learning/learning-journal.json`

```json
{
  "entries": [
    {
      "date": "2026-06-10",
      "focus_duration_minutes": 150,
      "diffuse_duration_minutes": 30,
      "topics_studied": ["贝叶斯定理", "MCMC采样"],
      "methods_used": ["费曼技巧", "主动回忆", "组块化"],
      "highlights": ["理解了先验和后验的直观含义"],
      "struggles": ["MCMC收敛诊断标准还不清楚"],
      "tomorrow_plan": ["用交错练习混合贝叶斯和MCMC题目"]
    }
  ]
}
```

## 配置文件格式

文件：`~/.meta-learning/config.json`

```json
{
  "default_target_type": "应用型",
  "daily_focus_minutes": 120,
  "preferred_methods": ["主动回忆", "费曼技巧"],
  "review_reminder_time": "09:00",
  "language": "zh",
  "discipline": "auto"
}
```

## 数据导入/导出

导出所有数据为单个备份文件：

```bash
# 导出
tar -czf meta-learning-backup-$(date +%Y%m%d).tar.gz ~/.meta-learning/

# 导入（覆盖现有数据）
tar -xzf meta-learning-backup-YYYYMMDD.tar.gz -C ~/
```

## 数据隐私

- 所有数据存储在本地文件系统，不自动上传
- 不包含个人身份信息（除非用户在 notes 字段中自行填写）
- 用户可随时删除 `~/.meta-learning/` 清空所有数据
- 备份文件由用户自行管理和传输
