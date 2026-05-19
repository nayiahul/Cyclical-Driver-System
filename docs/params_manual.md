# 参数手册

**版本**: v1.2 | **目标函数**: 最大化 Calmar (硬约束: 最大回撤 ≤ 35%)

## 核心敏感参数 (改动后系统行为剧烈变化)

| 参数 | 默认值 | 位置 | 含义 | 敏感度 |
|------|--------|------|------|--------|
| S1 R² 阈值 | 0.6 | `signals.py:compute_S1` | 利润加速度回归判定 | 高 — 提高=少选,降低=多选 |
| S2 合同负债 yoy 阈值 | 30% | `signals.py:compute_S2` | 订单信号触发 | 中 |
| S2 CAPEX yoy 阈值 | 20% | `signals.py:compute_S2` | 扩产信号触发 | 中 |
| BULL/STRUCT/BEAR 权重 | 0.50/0.35/0.20 | `screener.py:screen` | 三因子动态权重 | 高 |
| 行业暴露上限 | BULL 25% / STRUCT 15% / BEAR 10% | `screener.py:_apply_industry_constraint` | 单行业集中度 | 高 — 直接影响 Calmar |

## 稳健参数 (合理范围内变动影响不大)

| 参数 | 默认值 | 位置 |
|------|--------|------|
| IPO_LOCK_DAYS | 20 | `config/params.py` |
| RPS60_MIN | 65 | `config/params.py` (仅 S3 回测路径) |
| ROE_MIN_QUARTERS | 8 | `config/params.py` |
| PEG_MAX | 2.5 | `config/params.py` |
| 极端通道跌幅 | 15% | `config/params.py` |
| S1 低基数阈值 | 1000 万 | `signals.py:compute_S1` |
| S1 洗大澡阈值 | 150pp | `signals.py:compute_S1` |
| PEG growth cap | [5%, 50%] | `screener.py:screen_growth` |
| 拐点 RPS60 阈值 | 55 | `screener.py:screen_growth` |
| 拥挤度惩罚阈值 | 20% | `screener.py:_apply_industry_constraint` |

## v1.2 诊断参数 (仅观察，不参与评分)

| 参数 | 含义 |
|------|------|
| `factor_corr_*.csv` | 因子相关性矩阵 |
| `ind_weight_pct` | 行业在 TopN 中的占比 |
| `liquidity_flag` | PE 推断的规模分档 |
| `style_hint` | 成长/价值/均衡 标记 |
| `data_date` | 数据截止日期 |
