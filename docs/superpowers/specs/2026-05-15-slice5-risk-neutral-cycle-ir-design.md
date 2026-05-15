# Slice 5: 风险中性化 + 周期分层 IR 设计文档

**日期**: 2026-05-15
**关联**: V4.2 周期驱动三因子动态选股系统
**基于**: Slice 4（正交+IR+排雷，17.76% 年化，夏普 0.50）
**目标**: 用风险中性化消除 Beta 等系统性风险对信号的污染，用周期分层 IR 让因子权重随市场状态自适应

---

## 1. 目标

1. 风险中性化：动量信号（S3/S4）可能被高 Beta 污染——牛市高 Beta 股动量强但不代表 Alpha。横截面回归剥除 4 个风险因子后取残差。
2. 周期分层 IR：当前 IR 用全周期 IC，牛/熊/结构市下各因子有效性不同（牛市动量有效、熊市防御有效），分层计算让权重自适应市场状态。

## 2. 架构

```
新增:
risk_factors.py        # 4个风险因子计算
neutralizer.py         # 横截面回归残差提取

修改:
weights.py             # +CycleIRWeightManager（周期分层IR）
signals.py             # 链路插入中性化 + 改用CycleIR
```

信号链路（Slice 4 → Slice 5）：

```
S3,S4,S5,S7
    │ [新]
    ▼
risk_factors.py → Beta, Size, Vol, Illiq
    │ [新]
    ▼
neutralizer.py → 横截面回归取残差
    │
    ▼
orthogonalizer.py → F3,F4,F5,F7
    │
    ▼
weights.py → [新] 周期分层IR权重
    │
    ▼
Alpha = Σ w_j × F_j
```

## 3. 模块详设

### 3.1 risk_factors.py — 风险因子计算

全部数据来自已缓存的 `data/cache/daily_prices/`，无需新数据源。

| 因子 | 计算 | 窗口 |
|------|------|------|
| Beta | 个股 252 日日收益 vs 沪深300日收益的 OLS 斜率 | 252日 |
| Size | log(close × volume_20d_mean) | 20日 |
| Volatility | 60 日日收益标准差 | 60日 |
| Illiquidity | Amihud: mean(\|日收益\| / 日成交额) × 10^6，取对数 | 20日 |

沪深300指数数据使用 `regime/indicators.py` 中已有的 `_load_index_data()`。

**接口**：
```python
def compute_risk_factors(t_date: str, codes: list[str]) -> pd.DataFrame:
    """返回 N×4 DataFrame，列=[beta, size, volatility, illiquidity]"""
```

### 3.2 neutralizer.py — 风险中性化

对每个原始信号 S_i（非 NaN 股票），做 OLS 回归：

```
S_i = α + β₁·Beta + β₂·Size + β₃·Volatility + β₄·Illiquidity + ε
```

取残差 ε 作为去风险后的因子暴露。NaN 信号残差置 0。

**接口**：
```python
def neutralize(
    signals: dict[str, np.ndarray],
    risk_factors: pd.DataFrame,
) -> dict[str, np.ndarray]:
    """返回残差因子 {name: N×1 array}"""
```

### 3.3 weights.py 扩展 — CycleIRWeightManager

继承 `IRWeightManager`，增加 Regime 感知。

**改动**：
- IC 历史按 BULL/STRUCT/BEAR 分层存储（`ic_history_bull`, `ic_history_struct`, `ic_history_bear`）
- `get_weights(regime)` — 取当前 Regime 对应的 IC 子集计算权重
- 若当前 Regime 子集 < 12 个月 → 回退全周期 IC
- 冷启动（总历史 < 36 个月）→ 等权

Regime 判定复用 `regime/detector.py` 的 `detect_regime(t_date)`。

```python
class CycleIRWeightManager(IRWeightManager):
    def get_weights(self, regime: str) -> dict[str, float]:
        """按 Regime 分层取 IC 子集，计算 IR 权重"""
```

### 3.4 引擎集成

`signals.py` 的 `compute_alpha` 链路重组：

```python
def compute_alpha(t_date: str, codes: list[str]) -> dict[str, float]:
    # 1. 原始信号（不改）
    s3, s4, s5, s7 = ...

    # 2. 风险因子 + 中性化（新增）
    risk = compute_risk_factors(t_date, codes)
    neutralized = neutralize(
        {"S3": s3_arr, "S4": s4_arr, "S5": s5_arr, "S7": s7_arr},
        risk,
    )

    # 3. 正交化（不改）
    orthogonal = symmetric_orthogonalize(neutralized, blocks)

    # 4. 周期分层IR权重（改：get_weights → get_weights(regime)）
    regime_result = detect_regime(t_date)
    weights = _ir_manager.get_weights(regime_result.regime)

    # 5. 合成（不改）
    Alpha = Σ w_j × F_j
```

`backtest/engine.py` **不改**——接口保持 `compute_alpha(t_date, codes)`。

## 4. 项目目录（更新后）

```
周期驱动因子系统/
├── main.py
├── run_slice4.py
├── risk_factors.py              # 新增
├── neutralizer.py               # 新增
├── orthogonalizer.py
├── weights.py                   # 修改
├── valuation_filter.py
├── signals.py                   # 修改
├── industry.py
├── regime/
│   ├── detector.py              # 复用 detect_regime
│   └── indicators.py            # 复用 _load_index_data
├── backtest/engine.py           # 不改
└── config/params.py
```

## 5. 成功标准

- [ ] 4 个风险因子独立可运行，覆盖率 > 80%
- [ ] 中性化后信号与风险因子相关系数 ≈ 0
- [ ] 周期分层 IR 在 36 个月后按 Regime 分层启用
- [ ] 回测 2015-2024 无异常
- [ ] 夏普 vs Slice 4（0.50）有改善趋势

## 6. 已知局限

- Beta 用 Size 代理市值（无总股本数据），不做 log 变换
- Size 用收盘价×20日均成交量代理（无总股本字段）——方向正确但量纲不准
- 中性化用 OLS 不做 WLS（不做异方差修正）
- 不做 Ledoit-Wolf + 风险预算优化器（留给 Slice 6 或后续）
- 不做动态熔断（留给后续）
