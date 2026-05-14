# Slice 2: 市场周期识别 + 仓位调节 设计文档

**日期**: 2026-05-15
**关联**: V4.2 周期驱动三因子动态选股系统
**基于**: Slice 1 等权回测基准（13.44% 年化，-55.56% 最大回撤）
**目标**: 验证"识别熊市→减仓→降低回撤"核心假设

---

## 1. 目标

在 Slice 1 等权回测基础上增加市场周期识别层，用 Regime 驱动仓位调节：
- 牛市/结构市满仓（100%），熊市降至 60%
- 40% 剩余资金留作现金
- 对比 Slice 1 基准，验证回撤改善幅度

## 2. 架构

```
新增:
regime/
├── __init__.py
├── indicators.py         # 5维度指标计算
└── detector.py           # 状态判定 + 极端快速通道

修改:
├── config/params.py      # + 周期判定阈值 + 仓位映射
└── backtest/engine.py    # + Regime驱动仓位调节（∼10行）
```

数据流：
```
indicators.py (5维度月度序列)
    │
detector.py (Regime + RegimeScore)
    │
engine.py (仓位 = 等权 × position_cap)
```

## 3. 模块详设

### 3.1 config/params.py 新增

```python
# 周期判定阈值
INDEX_DROP_20D = 0.15       # 指数急跌：20日跌幅>15%
MARGIN_WEEKLY_DROP = -0.10  # 流动性枯竭：单周变化<-10%
V_REBOUND_10D = 0.12        # V型反转：10日反弹>12%
BREADTH_BULL = 0.55         # 广度牛市阈值
BREADTH_BEAR = 0.40         # 广度熊市阈值
NEW_HIGH_BULL = 0.08        # 创新高牛市阈值
NEW_HIGH_BEAR = 0.03        # 创新高熊市阈值
PE_DROP_BEAR = -0.05        # PE趋势熊市阈值
BULL_VOTE = 3               # 牛市最少命中项数
BEAR_CONFIRM_MONTHS = 2     # 状态确认月数
BEAR_WEEKLY_CONFIRM = 4     # 熊市周度确认

# 仓位映射
POSITION_CAP = {"BULL": 1.0, "STRUCT": 1.0, "BEAR": 0.60}
```

### 3.2 regime/indicators.py

所有函数输入 `trade_dates: list[str]`（YYYYMMDD 列表），返回 `pd.DataFrame`，index 为 YYYYMM。

| 函数 | 数据源 | 输出列 | 缓存路径 |
|------|--------|--------|---------|
| `index_trend(trade_dates)` | `ak.stock_zh_index_daily("sz399300")` | close, ma60, ma120, ma200 | `data/cache/index_399300.csv` |
| `market_breadth(trade_dates)` | `ak.stock_a_high_low_statistics("all")` | breadth_ratio (high120/(high120+low120) 20日均值) | `data/cache/high_low_stats.csv` |
| `new_high_ratio(trade_dates)` | 同上 | new_high_pct (high120/总数) | 同上 |
| `risk_appetite(trade_dates)` | `ak.stock_market_pe_lg("上证A股")` | pe_60d_change (市盈率60日变化率) | `data/cache/market_pe.csv` |
| `liquidity(trade_dates)` | `ak.macro_china_market_margin_sh/sz` | margin_weekly_change (两市融资余额合计周环比) | `data/cache/margin_data.csv` |

### 3.3 regime/detector.py

**输出**：
```python
@dataclass
class RegimeResult:
    regime: str           # "BULL" | "STRUCT" | "BEAR"
    score: float          # 0.0 - 1.0
    details: dict         # {index: bool, breadth: bool, new_high: bool, risk: bool, liquidity: bool}
```

**核心函数**：
```python
def detect_regime(t_date: str) -> RegimeResult:
    """给定月末确认日，返回下月生效的 Regime"""

def _check_extreme(t_date: str) -> RegimeResult | None:
    """极端快速通道检查，非极端时返回 None"""
```

**常规判定规则**：

| 维度 | 牛市条件 | 熊市条件 |
|------|---------|---------|
| 指数趋势 | close > ma200 且 ma60 > ma120 | close < ma200 且 ma60 < ma120 |
| 市场广度(代理) | 新高占比20日均值 > 0.55 | 新高占比20日均值 < 0.40 |
| 创新高比例 | high120占比 > 0.08 | high120占比 < 0.03 |
| 风险偏好(代理) | PE 60日变化率 > 0 | PE 60日变化率 < -0.05 |
| 流动性 | 融资余额连续3周净流入 | 连续3周净流出 |

**状态切换**：
- 结构市 → 牛市：连续 2 个月牛市条件 ≥ 3 项
- 结构市 → 熊市：广度 + 创新高同时跌破阈值，或指数破 MA200 且广度 < 0.40 持续 4 周
- RegimeScore = 5 项条件满足比例，取近 2 月均值

**极端快速通道**（T 日收盘触发，T+1 生效）：
- 指数急跌：滚动 20 日跌幅 > 15% → 直接熊市
- 流动性枯竭：融资余额单周变化 < -10% → 直接熊市
- V 型反转：10 日反弹 > 12% 且上涨家数连续 3 日 > 70% → 恢复为结构性
- 极端退出：快速通道进入的熊市需维持结构市条件 ≥ 1 个月才允许向上切换

### 3.4 backtest/engine.py 修改

在 `run_backtest` 调仓逻辑中插入两行：

```python
# 现有: universe = get_universe(t_date)
# 新增 ↓
from regime.detector import detect_regime
regime_result = detect_regime(t_date)
position_cap = POSITION_CAP[regime_result.regime]

# 现有: target_weights = {c: min(1/n, 0.08) for c in codes}
# 新增: 仓位上限缩放
target_weights = {c: w * position_cap for c, w in target_weights.items()}
```

日志输出每期 Regime 和仓位上限，其余逻辑不变。

### 3.5 目录结构（更新后）

```
周期驱动因子系统/
├── main.py
├── trade_calendar.py
├── universe.py
├── regime/                   # 新增
│   ├── __init__.py
│   ├── indicators.py
│   └── detector.py
├── backtest/
│   ├── __init__.py
│   └── engine.py             # 修改
├── config/
│   ├── __init__.py
│   └── params.py             # 修改
├── output/
├── data/cache/
└── docs/
```

## 4. 成功标准

- [ ] 5 个指标函数各自可独立运行，输出 2015-2024 月度序列
- [ ] Regime 序列合理：2015H2 熊市、2016-2017 结构/牛市、2018 熊市、2019-2020 结构/牛市、2022 熊市、2024 结构
- [ ] 极端快速通道正确触发 2015 年 6-8 月股灾 → 直接熊市
- [ ] 回测 2015-2024 无异常，输出 Slice 2 净值
- [ ] 最大回撤相比 Slice 1（-55.56%）显著降低

## 5. 已知局限

- 市场广度用新高占比代理，非实际上涨下跌家数
- 风险偏好用全市场 PE 趋势代理，非实际高PE vs 低PE分层收益差
- 暂不实现极端通道的波动率爆炸条件（V4.2 2.3节第三条），因 AKShare 无历史波动率直接接口
- RegimeScore 暂不用于 λ 插值（留给 Slice 3 因子权重层）
