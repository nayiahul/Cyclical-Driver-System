# Slice 2: 市场周期识别 + 仓位调节 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在等权回测基础上增加市场周期识别层，用 Regime 驱动仓位调节（牛/结构满仓，熊市 60%），验证回撤改善

**Architecture:** 新增 `regime/` 包（indicators.py → detector.py），修改 engine.py（~10 行）插入 Regime 判定和仓位缩放

**Tech Stack:** Python 3.10, pandas, numpy, akshare, loguru

**数据源适配**：`stock_a_high_low_statistics` 仅有 2 年历史，维度 2/3 改用指数层面代理

---

## 文件结构映射

| 文件 | 职责 | 内部依赖 |
|------|------|---------|
| `config/params.py` | 新增周期判定阈值 + 仓位映射 | 无 |
| `regime/__init__.py` | 包初始化 | 无 |
| `regime/indicators.py` | 5维度月度指标序列 | AKShare, config, trade_calendar |
| `regime/detector.py` | 状态机判定 + 极端通道 | indicators, config |
| `backtest/engine.py` | +Regime 驱动仓位缩放 | detector, config |

依赖链: indicators → detector → engine，单向无循环

---

### Task 1: 更新 config/params.py

**Files:**
- Modify: `config/params.py`

- [ ] **Step 1: 追加周期判定阈值和仓位映射**

在文件末尾追加：

```python
# ============================================================
# 市场周期判定阈值
# ============================================================

# 极端快速通道
INDEX_DROP_20D = 0.15        # 指数急跌：20交易日跌幅 > 15%
MARGIN_WEEKLY_DROP = -0.10   # 流动性枯竭：融资余额单周变化 < -10%
V_REBOUND_10D = 0.12         # V型反转：10交易日反弹 > 12%

# 常规判定 — 牛市阈值
BREADTH_BULL = 0.55          # 广度(代理)：指数>MA20占比 > 55%
NEW_HIGH_BULL = 0.05         # 创新高(代理)：指数距52周高点 < 5%
PE_CHANGE_BULL = 0.0         # 风险偏好：PE 60日变化 > 0

# 常规判定 — 熊市阈值
BREADTH_BEAR = 0.40          # 广度(代理)：指数>MA20占比 < 40%
NEW_HIGH_BEAR = 0.15         # 创新高(代理)：指数距52周高点 > 15%
PE_CHANGE_BEAR = -0.05       # 风险偏好：PE 60日变化 < -5%

# 状态切换
BULL_VOTE = 3                # 牛市最少命中项数（共5项）
BEAR_CONFIRM_MONTHS = 2      # 结构→牛市需连续确认月数
BEAR_WEEKLY_CONFIRM = 4      # 熊市需维持周数

# 仓位映射
POSITION_CAP = {"BULL": 1.0, "STRUCT": 1.0, "BEAR": 0.60}
```

- [ ] **Step 2: 验证导入**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "from config.params import POSITION_CAP, BULL_VOTE; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add config/params.py
git commit -m "feat: add regime detection thresholds and position cap config"
```

---

### Task 2: 创建 regime/indicators.py

**Files:**
- Create: `regime/__init__.py`
- Create: `regime/indicators.py`

- [ ] **Step 1: 创建包初始化文件**

```bash
mkdir -p regime
touch regime/__init__.py
```

- [ ] **Step 2: 实现 index_trend — 指数趋势指标**

```python
"""5维度市场周期指标计算"""
import os

import akshare as ak
import numpy as np
import pandas as pd
from loguru import logger

from config.params import (
    BREADTH_BEAR, BREADTH_BULL,
    NEW_HIGH_BEAR, NEW_HIGH_BULL,
)
from trade_calendar import get_trade_calendar

INDEX_CACHE = "data/cache/index_399300.csv"
PE_CACHE = "data/cache/market_pe.csv"
MARGIN_CACHE = "data/cache/margin_data.csv"


def _load_index_data() -> pd.DataFrame:
    """加载沪深300日线，缓存到CSV"""
    if os.path.exists(INDEX_CACHE):
        df = pd.read_csv(INDEX_CACHE, dtype={"date": str})
        df["date"] = pd.to_datetime(df["date"])
        return df

    raw = ak.stock_zh_index_daily(symbol="sz399300")
    df = raw[["date", "close"]].copy()
    df["close"] = df["close"].astype(float)
    os.makedirs(os.path.dirname(INDEX_CACHE), exist_ok=True)
    df.to_csv(INDEX_CACHE, index=False)
    logger.info(f"沪深300日线已缓存: {len(df)} 条")
    return df


def index_trend(trade_dates: list[str]) -> pd.DataFrame:
    """
    计算沪深300趋势指标。

    Returns:
        DataFrame index=YYYYMM, columns=[close, ma60, ma120, ma200,
        above_ma200, ma60_gt_ma120]
    """
    df = _load_index_data()
    df = df.set_index("date").sort_index()
    df["ma60"] = df["close"].rolling(60).mean()
    df["ma120"] = df["close"].rolling(120).mean()
    df["ma200"] = df["close"].rolling(200).mean()

    # 对齐到交易日
    trade_idx = pd.to_datetime(trade_dates, format="%Y%m%d")
    aligned = df.reindex(trade_idx, method="ffill")

    result = pd.DataFrame({
        "close": aligned["close"].values,
        "ma60": aligned["ma60"].values,
        "ma120": aligned["ma120"].values,
        "ma200": aligned["ma200"].values,
        "above_ma200": (aligned["close"] > aligned["ma200"]).values,
        "ma60_gt_ma120": (aligned["ma60"] > aligned["ma120"]).values,
    }, index=[d[:6] for d in trade_dates])
    return result


def market_breadth(trade_dates: list[str]) -> pd.DataFrame:
    """
    市场广度代理：指数收盘价 > MA20 的交易日占比（过去60日）。

    Returns:
        DataFrame index=YYYYMM, columns=[breadth_ratio]
    """
    df = _load_index_data()
    df = df.set_index("date").sort_index()
    df["ma20"] = df["close"].rolling(20).mean()
    df["above_ma20"] = (df["close"] > df["ma20"]).astype(int)

    # 60日滚动窗口内 above_ma20 的均值
    df["breadth_ratio"] = df["above_ma20"].rolling(60).mean()

    trade_idx = pd.to_datetime(trade_dates, format="%Y%m%d")
    aligned = df.reindex(trade_idx, method="ffill")

    result = pd.DataFrame({
        "breadth_ratio": aligned["breadth_ratio"].values,
    }, index=[d[:6] for d in trade_dates])
    return result


def new_high_ratio(trade_dates: list[str]) -> pd.DataFrame:
    """
    创新高比例代理：指数距52周（250日）高点的距离。

    距离 < NEW_HIGH_BULL(5%) → 视为创新高状态
    距离 > NEW_HIGH_BEAR(15%) → 视为远离新高

    Returns:
        DataFrame index=YYYYMM, columns=[dist_from_high]
    """
    df = _load_index_data()
    df = df.set_index("date").sort_index()
    df["high_250"] = df["close"].rolling(250).max()
    df["dist_from_high"] = (df["high_250"] - df["close"]) / df["high_250"]

    trade_idx = pd.to_datetime(trade_dates, format="%Y%m%d")
    aligned = df.reindex(trade_idx, method="ffill")

    result = pd.DataFrame({
        "dist_from_high": aligned["dist_from_high"].values,
    }, index=[d[:6] for d in trade_dates])
    return result


def risk_appetite(trade_dates: list[str]) -> pd.DataFrame:
    """
    风险偏好代理：全市场PE的60日变化率。

    Returns:
        DataFrame index=YYYYMM, columns=[pe_60d_change]
    """
    if os.path.exists(PE_CACHE):
        pe_df = pd.read_csv(PE_CACHE, dtype={"日期": str})
    else:
        raw = ak.stock_market_pe_lg(symbol="上证A股")
        pe_df = raw[["日期", "市盈率"]].copy()
        pe_df.columns = ["date", "pe"]
        pe_df["pe"] = pe_df["pe"].astype(float)
        os.makedirs(os.path.dirname(PE_CACHE), exist_ok=True)
        pe_df.to_csv(PE_CACHE, index=False)

    pe_df["date"] = pd.to_datetime(pe_df["date"])
    pe_df = pe_df.set_index("date").sort_index()
    pe_df["pe_60d_change"] = pe_df["pe"].pct_change(60)

    trade_idx = pd.to_datetime(trade_dates, format="%Y%m%d")
    aligned = pe_df.reindex(trade_idx, method="ffill")

    result = pd.DataFrame({
        "pe_60d_change": aligned["pe_60d_change"].values,
    }, index=[d[:6] for d in trade_dates])
    return result


def liquidity(trade_dates: list[str]) -> pd.DataFrame:
    """
    流动性指标：两市融资余额合计的周环比变化。

    Returns:
        DataFrame index=YYYYMM, columns=[margin_weekly_change]
    """
    if os.path.exists(MARGIN_CACHE):
        margin_df = pd.read_csv(MARGIN_CACHE, dtype={"日期": str})
    else:
        sh = ak.macro_china_market_margin_sh()
        sz = ak.macro_china_market_margin_sz()
        sh_df = sh[["日期", "融资融券余额"]].copy()
        sh_df.columns = ["date", "balance_sh"]
        sz_df = sz[["日期", "融资融券余额"]].copy()
        sz_df.columns = ["date", "balance_sz"]
        margin_df = pd.merge(sh_df, sz_df, on="date", how="inner")
        margin_df["total_balance"] = (
            margin_df["balance_sh"].astype(float) + margin_df["balance_sz"].astype(float)
        )
        os.makedirs(os.path.dirname(MARGIN_CACHE), exist_ok=True)
        margin_df.to_csv(MARGIN_CACHE, index=False)

    margin_df["date"] = pd.to_datetime(margin_df["date"])
    margin_df = margin_df.set_index("date").sort_index()
    # 周环比：5个交易日变化
    margin_df["weekly_change"] = margin_df["total_balance"].pct_change(5)
    # 连续3周方向：3期滚动求和符号
    margin_df["flow_sign"] = np.sign(margin_df["weekly_change"])
    margin_df["flow_3week"] = margin_df["flow_sign"].rolling(3).sum()

    trade_idx = pd.to_datetime(trade_dates, format="%Y%m%d")
    aligned = margin_df.reindex(trade_idx, method="ffill")

    result = pd.DataFrame({
        "margin_weekly_change": aligned["weekly_change"].values,
        "flow_3week": aligned["flow_3week"].values,
    }, index=[d[:6] for d in trade_dates])
    return result
```

- [ ] **Step 3: 验证 — 测试每个指标函数**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
from trade_calendar import get_rebalance_dates, get_t_date
from regime.indicators import index_trend, market_breadth, new_high_ratio, risk_appetite, liquidity

# 生成T日序列（每月末）
rebalance_dates = get_rebalance_dates('20150101', '20241231')
t_dates = [get_t_date(d) for d in rebalance_dates]

# 逐个测试
it = index_trend(t_dates)
print(f'index_trend: {len(it)} months, cols={list(it.columns)}')
print(it.head(2))

mb = market_breadth(t_dates)
print(f'market_breadth: {len(mb)} months, last value={mb.iloc[-1,0]:.3f}')

nh = new_high_ratio(t_dates)
print(f'new_high_ratio: {len(nh)} months, last value={nh.iloc[-1,0]:.3f}')

ra = risk_appetite(t_dates)
print(f'risk_appetite: {len(ra)} months, last PE change={ra.iloc[-1,0]:.3f}')

liq = liquidity(t_dates)
print(f'liquidity: {len(liq)} months, cols={list(liq.columns)}')
print('All indicators OK')
"
```

预期: 5 个函数各输出 120 个月度数据，列名正确

- [ ] **Step 4: 提交**

```bash
git add regime/__init__.py regime/indicators.py data/cache/
git commit -m "feat: add 5-dimension regime indicators module"
```

---

### Task 3: 创建 regime/detector.py

**Files:**
- Create: `regime/detector.py`

- [ ] **Step 1: 实现 RegimeResult 和 detect_regime**

```python
"""市场周期状态判定"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from loguru import logger

from config.params import (
    BEAR_CONFIRM_MONTHS, BEAR_WEEKLY_CONFIRM,
    BREADTH_BEAR, BREADTH_BULL,
    BULL_VOTE, INDEX_DROP_20D,
    MARGIN_WEEKLY_DROP, NEW_HIGH_BEAR, NEW_HIGH_BULL,
    PE_CHANGE_BEAR, PE_CHANGE_BULL, V_REBOUND_10D,
)
from regime.indicators import (
    index_trend, liquidity, market_breadth, new_high_ratio, risk_appetite,
)
from trade_calendar import get_t_date, get_trade_calendar


@dataclass
class RegimeResult:
    regime: str        # "BULL" | "STRUCT" | "BEAR"
    score: float       # 0.0 - 1.0
    details: dict      # 各维度布尔判定


def detect_regime(t_date: str) -> RegimeResult:
    """
    给定月末确认日，返回下月生效的 Regime。

    判定规则：
    1. 先检查极端快速通道
    2. 再计算5维度布尔判定
    3. 根据历史状态和当前条件切换
    """
    # 获取T日前6个月的rebalance T日期序列，用于计算指标和状态历史
    # 简化：直接用当前t_date和之前的数据计算
    cal = get_trade_calendar("20140101", t_date)
    trade_dates = cal["trade_date"].tolist()

    # 计算5维度指标（基于截至t_date的所有数据）
    it = index_trend(trade_dates)
    mb = market_breadth(trade_dates)
    nh = new_high_ratio(trade_dates)
    ra = risk_appetite(trade_dates)
    liq = liquidity(trade_dates)

    # 取最后一个月的值（即t_date对应月份的指标）
    t_ym = t_date[:6]
    if t_ym not in it.index:
        return RegimeResult(regime="STRUCT", score=0.5, details={})

    idx_close = it.loc[t_ym, "close"]
    idx_above_ma200 = bool(it.loc[t_ym, "above_ma200"])
    idx_ma60_gt_ma120 = bool(it.loc[t_ym, "ma60_gt_ma120"])
    breadth_val = mb.loc[t_ym, "breadth_ratio"]
    nh_val = nh.loc[t_ym, "dist_from_high"]
    pe_change = ra.loc[t_ym, "pe_60d_change"]
    margin_weekly = liq.loc[t_ym, "margin_weekly_change"]
    flow_3week = liq.loc[t_ym, "flow_3week"]

    # === 极端快速通道 ===
    # 指数急跌
    if len(it) >= 20:
        close_20d_ago = it["close"].iloc[-21]  # 21个交易日前
        drop_20d = (idx_close - close_20d_ago) / close_20d_ago
        if drop_20d < -INDEX_DROP_20D:
            logger.warning(f"极端通道触发: 指数20日跌幅 {drop_20d:.1%} @ {t_date}")
            return _extreme_bear(t_date)

    # 流动性枯竭
    if not np.isnan(margin_weekly) and margin_weekly < MARGIN_WEEKLY_DROP:
        logger.warning(f"极端通道触发: 融资余额周变化 {margin_weekly:.1%} @ {t_date}")
        return _extreme_bear(t_date)

    # === 5维度布尔判定 ===
    details = {
        "index": idx_above_ma200 and idx_ma60_gt_ma120,           # 牛市
        "breadth": breadth_val > BREADTH_BULL,                     # 牛市
        "new_high": nh_val < NEW_HIGH_BULL,                        # 牛市（距离<阈值）
        "risk": pe_change > PE_CHANGE_BULL,                        # 牛市
        "liquidity": not np.isnan(flow_3week) and flow_3week > 0,  # 牛市(连续净流入)
    }
    bull_count = sum(details.values())

    bear_details = {
        "index": (not idx_above_ma200) and (not idx_ma60_gt_ma120),
        "breadth": breadth_val < BREADTH_BEAR,
        "new_high": nh_val > NEW_HIGH_BEAR,
        "risk": pe_change < PE_CHANGE_BEAR,
        "liquidity": not np.isnan(flow_3week) and flow_3week < -2,
    }
    bear_count = sum(bear_details.values())

    # RegimeScore: 牛市条件满足比例（如果有熊市倾向则降低）
    score = bull_count / 5.0
    if bear_count >= 3:
        score = min(score, 0.35)

    # 状态判定
    if bear_count >= 4:
        regime = "BEAR"
    elif bull_count >= BULL_VOTE:
        regime = "BULL"
    else:
        regime = "STRUCT"

    return RegimeResult(regime=regime, score=score, details=details)


def _extreme_bear(t_date: str) -> RegimeResult:
    """极端通道熊市"""
    return RegimeResult(
        regime="BEAR",
        score=0.0,
        details={"extreme": True},
    )
```

- [ ] **Step 2: 验证 — 检查关键日期的 Regime**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
from regime.detector import detect_regime

# 关键历史时刻验证
tests = {
    '20150630': 'BEAR',   # 2015股灾开始
    '20160129': 'BEAR',   # 2016熔断后
    '20171229': 'BULL',   # 2017白马牛
    '20181228': 'BEAR',   # 2018熊市底
    '20200630': 'BULL',   # 2020疫情后反弹
    '20240329': 'STRUCT', # 2024结构市
}
for dt, expected in tests.items():
    r = detect_regime(dt)
    match = '✓' if r.regime == expected else f'✗ (got {r.regime})'
    print(f'{dt}: {r.regime} score={r.score:.2f} bull={sum(r.details.values())}/5 {match}')
"
```

- [ ] **Step 3: 提交**

```bash
git add regime/detector.py
git commit -m "feat: add regime state machine with extreme channel detection"
```

---

### Task 4: 修改 backtest/engine.py 集成 Regime

**Files:**
- Modify: `backtest/engine.py`

- [ ] **Step 1: 在 run_backtest 调仓逻辑中插入 Regime 判定**

在 `backtest/engine.py` 中添加导入：

```python
from config.params import (
    END_DATE,
    INITIAL_CAPITAL,
    MAX_SINGLE_WEIGHT,
    MIN_HOLDINGS,
    POSITION_CAP,        # 新增
    START_DATE,
    TOTAL_COST_RATE,
)
from regime.detector import detect_regime  # 新增
```

在调仓逻辑中（现有 `universe = get_universe(t_date)` 之后），插入：

```python
            # 周期判定与仓位调节
            regime_result = detect_regime(t_date)
            position_cap = POSITION_CAP.get(regime_result.regime, 1.0)
            logger.info(
                f"{day}: regime={regime_result.regime} "
                f"score={regime_result.score:.2f} cap={position_cap:.0%}"
            )
```

在目标权重计算后，应用仓位缩放：

```python
            # 应用仓位上限缩放（熊市自动降至60%）
            target_weights = {c: w * position_cap for c, w in target_weights.items()}
```

- [ ] **Step 2: 验证 — 检查导入和结构**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "from backtest.engine import run_backtest; print('engine imports OK')"
```

- [ ] **Step 3: 提交**

```bash
git add backtest/engine.py
git commit -m "feat: integrate regime-driven position sizing into backtest engine"
```

---

### Task 5: 运行回测并对比基准

**Files:**
- 无新建文件

- [ ] **Step 1: 运行 Slice 2 回测**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
import os
from backtest.engine import run_backtest

result = run_backtest('20150101', '20241231')
stats = result.stats
print('\n=== Slice 2 回测统计 ===')
for k, v in stats.items():
    print(f'  {k}: {v}')

os.makedirs('output', exist_ok=True)
result.nav_series.to_csv('output/nav_slice2.csv', header=['nav'])
result.trades.to_csv('output/trades_slice2.csv', index=False)
print('\n已保存至 output/nav_slice2.csv')
"
```

- [ ] **Step 2: 对比 Slice 1 基准**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
import pandas as pd
import numpy as np

s1 = pd.read_csv('output/nav.csv', index_col=0)
s2 = pd.read_csv('output/nav_slice2.csv', index_col=0)

def stats(nav):
    ret = nav.pct_change().dropna()
    years = len(ret) / 252
    total = (nav.iloc[-1,0] / nav.iloc[0,0]) - 1
    ann = (1 + total) ** (1/years) - 1
    vol = ret.std().values[0] * np.sqrt(252)
    sharpe = (ann - 0.02) / vol
    cummax = nav.cummax()
    dd = ((nav.values - cummax.values) / cummax.values).min()
    return ann, vol, sharpe, dd, total

s1_stats = stats(s1)
s2_stats = stats(s2)

print(f'指标              | Slice 1(等权) | Slice 2(周期) | 改善')
print(f'年化收益          | {s1_stats[0]:.2%}       | {s2_stats[0]:.2%}       |')
print(f'年化波动          | {s1_stats[1]:.2%}       | {s2_stats[1]:.2%}       |')
print(f'夏普比率          | {s1_stats[2]:.2f}         | {s2_stats[2]:.2f}         |')
print(f'最大回撤          | {s1_stats[3]:.2%}      | {s2_stats[3]:.2%}      |')
print(f'累计收益          | {s1_stats[4]:.2%}       | {s2_stats[4]:.2%}       |')
"
```

- [ ] **Step 3: 提交最终结果**

```bash
git add output/
git commit -m "feat: complete Slice 2 backtest with regime-driven position sizing"
```

---

## 成功标准对照

| 标准 | 验证方式 |
|------|---------|
| 5个指标函数独立输出月度序列 | Task 2 Step 3: 各120个月 |
| Regime序列合理（2015熊、2017牛、2018熊、2020牛） | Task 3 Step 2: 关键日期检查 |
| 极端通道触发2015股灾 | Task 3 Step 2: 20150630 → BEAR |
| 回测无异常，输出Slice 2净值 | Task 5 Step 1 |
| 最大回撤相比Slice 1改善 | Task 5 Step 2: Slice 2 回撤 < Slice 1 |
