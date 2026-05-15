# Slice 4: 因子处理流水线 设计文档

**日期**: 2026-05-15
**关联**: V4.2 周期驱动三因子动态选股系统
**基于**: Slice 1 等权基准（13.44% 年化，-55.56% 回撤）+ Slice 3 信号层（S3/S4/S5/S7 已实现）
**目标**: 用正交化消除信号共线性、IR 动态权重替代等权合成、估值排雷过滤泡沫股，验证是否超越全市场等权基准

---

## 1. 目标

解决 Slice 3 暴露的两个核心问题：
1. S5（ROE 稳定，覆盖 90%+）在等权合成中碾压 S3/S4（动量，覆盖 5-15%）
2. 无估值约束导致选入泡沫/垃圾股

## 2. 架构

```
新增:
orthogonalizer.py       # 分块对称正交化
weights.py              # IR 动态权重
valuation_filter.py     # 6条估值排雷硬约束

修改:
signals.py              # Alpha合成: 等权→正交化+IR权重
backtest/engine.py      # +估值排雷前置
```

数据流：
```
S3,S4,S5,S7
    │
orthogonalizer.py → F3,F4,F5,F7 (块内正交)
    │
weights.py → w3,w4,w5,w7 (IR滚动)
    │
Alpha = Σ w_j × F_j
    │
[engine.py: 估值排雷过滤 → Top100 Alpha]
```

## 3. 模块详设

### 3.1 orthogonalizer.py — 分块对称正交化

**分块**（当前 4 个已实现信号）：

| 块 | 信号 | 含义 | 正交后 |
|----|------|------|--------|
| 块1 | S3, S4 | 价格信号（动量+行业共振） | F3, F4 |
| 块2 | S5, S7 | 质量/防御（稳定性+现金流） | F5, F7 |

S1（利润加速度）、S2（产能扩张）、S6（毛利率/研发）暂未实现，对应块暂时为空。

**算法**（对称正交化）：

1. 块内构建 N×T 信号矩阵（N 只股票 × T 个月度截面），pairwise-complete 计算协方差矩阵 Σ
2. 对 Σ 特征值分解：Σ = V·D·V^T
3. 对称正交矩阵：L = V·D^(-1/2)·V^T
4. 正交因子：F_block = S_block · L

**特性**：
- 块内相关系数 → 0
- 块间保留原始相关性
- 对称矩阵保证 F_j 与原始 S_j 最大程度相似

**接口**：
```python
def symmetric_orthogonalize(
    signals: dict[str, np.ndarray],  # {name: N×1 array}
    blocks: list[list[str]],         # [["S3","S4"], ["S5","S7"]]
) -> dict[str, np.ndarray]:          # {name: N×1 array}
```

### 3.2 weights.py — IR 动态权重

**冷启动**（前 36 个月）：所有因子等权 `w_j = 1/n`

**IR 权重**（第 37 个月起）：
```
对每个正交因子 F_j：
  IC_j = 过去36个月月度 Rank IC 序列
  IR_j = mean(IC_j) / std(IC_j)
  w_j = max(0, IR_j) / Σ max(0, IR_k)
```

**回退**：所有因子 IR ≤ 0 → 等权分配

**接口**：
```python
def compute_factor_weights(
    factor_ic: dict[str, list[float]],
) -> dict[str, float]:
    """IR → 归一化权重"""

def rolling_ir_weights(
    factor_returns: dict[str, pd.Series],
    window: int = 36,
) -> dict[str, float]:
    """滚动计算 IR 权重"""
```

**Alpha 合成**：
```
Alpha = Σ w_j × F_j  （非NaN因子权重重归一化）
```

### 3.3 valuation_filter.py — 估值排雷

6 条硬约束，触发即剔除，不参与 Alpha 评分：

| # | 规则 | 数据源 | 备注 |
|---|------|--------|------|
| 1 | PE 为负且近两季净利润未环比改善 | 财务缓存（roe_weighted 趋势） | 利润质量 |
| 2 | 非经常性损益依赖 | 财务缓存（投资收益等字段不存在→用 ROE 波动代理） | 简化处理 |
| 3 | ST 股票 | universe 已过滤 | 不需重复 |
| 4 | 流动性后 20% | 收盘价×总股本（市值）+ 20 日成交额 | 滚动 2 年分位数 |
| 5 | PEG > 2.5 | 需 PE + 利润增速 | 利润增速用 ROE 变化趋势代理 |
| 6 | 股价距 200 日均线乖离率 > 120% | 已缓存日线 | 情绪泡沫 |

**审计非标**（#3）和**重大重组**（#6）无法从现有数据可靠获取，跳过。

**接口**：
```python
def apply_valuation_filter(
    t_date: str,
    codes: list[str],
    industry_map: dict[str, str],
) -> list[str]:
    """返回通过过滤的股票代码列表"""
```

### 3.4 引擎集成

在 `backtest/engine.py` 调仓逻辑中，universe 之后、Alpha 计算之前插入：

```python
# 估值排雷
filtered_codes = apply_valuation_filter(t_date, target_codes)

# Alpha计算（内部已正交化+IR权重）
alpha_scores = compute_alpha(t_date, filtered_codes)

# Top100等权
ranked = sorted(alpha_scores.items(), key=lambda x: x[1], reverse=True)
selected = [c for c, _ in ranked[:TOP_N_STOCKS]]
weight = min(1.0 / max(len(selected), 1), MAX_SINGLE_WEIGHT)
target_weights = {c: weight for c in selected}
```

`signals.py` 的 `compute_alpha` 改为：
1. 计算 S3, S4, S5, S7（现有）
2. 调用 `orthogonalizer.symmetric_orthogonalize` → F3, F4, F5, F7
3. 调用 `weights.rolling_ir_weights` → w3, w4, w5, w7
4. 合成 `Alpha = Σ w_j × F_j`

## 4. 项目目录（更新后）

```
周期驱动因子系统/
├── main.py
├── trade_calendar.py
├── universe.py
├── industry.py
├── signals.py                    # 修改
├── orthogonalizer.py             # 新增
├── weights.py                    # 新增
├── valuation_filter.py           # 新增
├── regime/
│   ├── __init__.py
│   ├── indicators.py
│   └── detector.py
├── backtest/
│   ├── __init__.py
│   └── engine.py                 # 修改
├── config/
│   ├── __init__.py
│   └── params.py
└── output/
```

## 5. 成功标准

- [ ] 正交化后块内相关系数 ≈ 0
- [ ] IR 权重在 36 个月后启用，前 36 月等权
- [ ] 估值排雷每月剔除率 5-15%
- [ ] 回测 2015-2024 无异常
- [ ] 夏普 vs Slice 1 有改善趋势（IR 权重前 3 年与等权相同，改善来自第 4-10 年）

## 6. 已知局限

- 审计非标、重大重组不做（缺少数据）
- PEG 计算用 ROE 变化代理利润增速（非精确一致预期增速）
- 非经常性损益依赖用 ROE 波动代理（简化）
- IR 使用全周期（不做周期分层，Slice 5 再做）
- 不做风险中性化（Slice 5）
- 不做协方差压缩 + 优化器（Slice 5）
