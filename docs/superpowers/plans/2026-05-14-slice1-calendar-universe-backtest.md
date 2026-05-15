# Slice 1: 交易日历 + 股票池 + 等权回测 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用最小实现验证"数据获取 → 股票池 → 调仓 → 净值"链路完整可运行

**Architecture:** 3 个独立模块（calendar / universe / backtest engine）+ 1 个入口 main.py。模块通过函数调用传递 DataFrame，回测引擎用纯 pandas 事件循环。

**Tech Stack:** Python 3.10, pandas, numpy, akshare, loguru

---

## 文件结构映射

| 文件 | 职责 | 内部依赖 |
|------|------|---------|
| `config/params.py` | 所有可配置常量 | 无 |
| `calendar.py` | 交易日历 + 调仓日列表 | AKShare, config |
| `universe.py` | 股票池获取与基础过滤 | AKShare, config, calendar |
| `backtest/engine.py` | 等权回测循环 + 净值记录 | calendar, universe, config |
| `main.py` | 入口，调用回测，打印统计 | 以上全部 |

---

### Task 1: 项目脚手架与依赖

**Files:**
- Create: `config/params.py`
- Create: `requirements.txt`
- Create: `data/cache/.gitkeep`
- Create: `output/.gitkeep`
- Create: `backtest/__init__.py`

- [ ] **Step 1: 创建目录结构**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
mkdir -p config data/cache output backtest
touch data/cache/.gitkeep output/.gitkeep backtest/__init__.py
```

- [ ] **Step 2: 写入 config/params.py**

```python
"""全局可配置常量"""

# 回测
INITIAL_CAPITAL = 100_000_000  # 初始资金 1亿
START_DATE = "20150101"
END_DATE = "20241231"

# 交易成本
COMMISSION_RATE = 0.0003   # 佣金
STAMP_TAX_RATE = 0.001     # 印花税（卖出）
SLIPPAGE_RATE = 0.0017     # 滑点
TOTAL_COST_RATE = COMMISSION_RATE + STAMP_TAX_RATE + SLIPPAGE_RATE  # 0.3%

# 组合约束
MAX_SINGLE_WEIGHT = 0.08   # 单票上限 8%
MIN_HOLDINGS = 15          # 最少持仓数
IPO_LOCK_DAYS = 20         # 新股上市后跳过交易日数

# 缓存
CACHE_DIR = "data/cache"
TRADE_CALENDAR_CACHE = "data/cache/trade_calendar.csv"
STOCK_LIST_CACHE = "data/cache/stock_list.csv"

# 输出
OUTPUT_DIR = "output"
```

- [ ] **Step 3: 写入 requirements.txt**

```
pandas>=2.0.0
numpy>=1.24.0
akshare>=1.12.0
loguru>=0.7.0
```

- [ ] **Step 4: 安装依赖**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/pip install pandas numpy akshare loguru
```

- [ ] **Step 5: 初始化 git 并提交**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
git init
git add -A
git commit -m "chore: project scaffolding with config and dependencies"
```

---

### Task 2: calendar.py — 交易日历

**Files:**
- Create: `calendar.py`

- [ ] **Step 1: 实现 get_trade_calendar（含缓存）**

```python
"""交易日历与调仓日期"""
import os
from datetime import datetime

import akshare as ak
import pandas as pd

from config.params import TRADE_CALENDAR_CACHE


def get_trade_calendar(start: str, end: str) -> pd.DataFrame:
    """
    获取A股交易日历。

    Args:
        start: 起始日期 "YYYYMMDD"
        end: 结束日期 "YYYYMMDD"

    Returns:
        DataFrame with columns: trade_date (str YYYYMMDD)
    """
    if os.path.exists(TRADE_CALENDAR_CACHE):
        df = pd.read_csv(TRADE_CALENDAR_CACHE, dtype={"trade_date": str})
        df = df[(df["trade_date"] >= start) & (df["trade_date"] <= end)]
        if len(df) > 0:
            return df.reset_index(drop=True)

    df = ak.tool_trade_date_hist_sina()
    df.columns = ["trade_date"]
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y%m%d")
    df = df.sort_values("trade_date").reset_index(drop=True)
    df.to_csv(TRADE_CALENDAR_CACHE, index=False)

    return df[(df["trade_date"] >= start) & (df["trade_date"] <= end)].reset_index(drop=True)
```

- [ ] **Step 2: 实现 get_rebalance_dates**

```python
def get_rebalance_dates(start: str, end: str) -> list[str]:
    """
    获取每月首个交易日列表（调仓日）。

    Args:
        start: 起始日期 "YYYYMMDD"
        end: 结束日期 "YYYYMMDD"

    Returns:
        list of date strings "YYYYMMDD"
    """
    cal = get_trade_calendar(start, end)
    cal["ym"] = cal["trade_date"].str[:6]
    first_days = cal.groupby("ym")["trade_date"].first()
    return first_days.tolist()
```

- [ ] **Step 3: 实现 get_t_date**

```python
def get_t_date(rebalance_date: str) -> str:
    """
    获取调仓日的前一个交易日（月末确认日）。

    Args:
        rebalance_date: 调仓日期 "YYYYMMDD"

    Returns:
        前一个交易日 "YYYYMMDD"
    """
    cal = get_trade_calendar("20000101", rebalance_date)
    if len(cal) < 2:
        raise ValueError(f"日历中找不到 {rebalance_date} 之前的交易日")
    return cal["trade_date"].iloc[-2]
```

- [ ] **Step 4: 验证 — 在 Python REPL 中测试**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
from calendar import get_trade_calendar, get_rebalance_dates, get_t_date

cal = get_trade_calendar('20150101', '20241231')
print(f'日历天数: {len(cal)}')
print(f'前5日: {cal.head().values.tolist()}')

dates = get_rebalance_dates('20150101', '20241231')
print(f'调仓月数: {len(dates)}')
print(f'前3个调仓日: {dates[:3]}')

# 验证每个调仓日都有前一个交易日
for d in dates[:5]:
    t = get_t_date(d)
    print(f'调仓日 {d} → T日 {t}')
"
```

预期: 日历 > 2400 天, 调仓月数 ≈ 120, T日 = 调仓日前一个交易日

- [ ] **Step 5: 提交**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
git add calendar.py data/cache/
git commit -m "feat: add trading calendar module with AKShare"
```

---

### Task 3: universe.py — 股票池

**Files:**
- Create: `universe.py`

- [ ] **Step 1: 实现 get_stock_list**

```python
"""股票池获取与基础过滤"""
import os
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

from config.params import STOCK_LIST_CACHE


def get_stock_list() -> pd.DataFrame:
    """
    获取全部A股基础信息。

    Returns:
        DataFrame with columns: code, name, list_date
    """
    if os.path.exists(STOCK_LIST_CACHE):
        return pd.read_csv(STOCK_LIST_CACHE, dtype={"code": str, "name": str})

    df = ak.stock_info_a_code_name()
    df = df.rename(columns={"code": "code", "name": "name"})
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["name"] = df["name"].astype(str)

    # 获取上市日期 — 通过 stock_zh_a_hist 取每只股票最早交易日
    # 为减少API调用，批量下载指数成分股历史并提取首次出现日期
    list_dates = _get_listing_dates(df["code"].tolist())
    df["list_date"] = df["code"].map(list_dates)

    df = df.dropna(subset=["list_date"])
    df.to_csv(STOCK_LIST_CACHE, index=False)
    return df
```

- [ ] **Step 2: 实现 _get_listing_dates 批量获取上市日期**

```python
def _get_listing_dates(codes: list[str]) -> dict[str, str]:
    """
    通过股票日线数据获取每只股票的最早交易日期（近似上市日期）。

    使用沪深300成分股的历史数据作为代理：
    — 先获取沪深300指数日线
    — 对于无法直接从成分股推断的股票，单次批量请求

    注意：AKShare 单次 stock_zh_a_hist 只能查单只股票，
    这里用 stock_info_a_code_name 返回中有 list_date 字段的情况直接使用。
    """
    # AKShare 的 stock_info_a_code_name 实际返回包含 list_date
    # 尝试直接获取
    try:
        df = ak.stock_info_a_code_name()
        if "list_date" in df.columns:
            date_map = {}
            for _, row in df.iterrows():
                code = str(row["code"]).zfill(6)
                ld = str(row.get("list_date", ""))
                if ld and ld != "nan":
                    date_map[code] = ld[:8]  # 取 YYYYMMDD
            return date_map
    except Exception:
        pass

    # 回退方案：对每只股票查最早数据（慢，但完整）
    date_map = {}
    for code in codes:
        try:
            hist = ak.stock_zh_a_hist(
                symbol=code, period="monthly",
                start_date="19900101", end_date="20241231",
                adjust="qfq"
            )
            if len(hist) > 0:
                date_map[code] = hist["日期"].iloc[0].replace("-", "")
        except Exception:
            continue
    return date_map
```

- [ ] **Step 3: 实现 get_universe 过滤逻辑**

```python
def get_universe(trade_date: str) -> pd.DataFrame:
    """
    获取指定交易日的可交易股票池。

    过滤条件：
    1. 已上市 (list_date <= trade_date)
    2. 非ST (名称不含 ST 或 *ST)
    3. 非新股首月 (list_date 早于 trade_date 至少 20 个交易日)

    Args:
        trade_date: 交易日期 "YYYYMMDD"

    Returns:
        DataFrame with columns: code, name
    """
    from calendar import get_trade_calendar
    from config.params import IPO_LOCK_DAYS

    stocks = get_stock_list()

    # 过滤1: 已上市
    listed = stocks[stocks["list_date"] <= trade_date]

    # 过滤2: 非ST
    not_st = listed[~listed["name"].str.contains(r"\*?ST", na=False)]

    # 过滤3: 非新股首月 — list_date 早于 trade_date 至少 IPO_LOCK_DAYS 个交易日
    cal = get_trade_calendar("19900101", trade_date)
    cal_dates = cal["trade_date"].tolist()
    try:
        t_idx = cal_dates.index(trade_date)
    except ValueError:
        return not_st.head(0)  # 非交易日，返回空

    lock_idx = max(0, t_idx - IPO_LOCK_DAYS)
    lock_date = cal_dates[lock_idx]
    filtered = not_st[not_st["list_date"] <= lock_date]

    return filtered[["code", "name"]].reset_index(drop=True)
```

- [ ] **Step 4: 添加淘汰日志**

```python
from loguru import logger


def get_universe(trade_date: str) -> pd.DataFrame:
    stocks = get_stock_list()
    total = len(stocks)

    listed = stocks[stocks["list_date"] <= trade_date]
    removed_not_listed = total - len(listed)

    not_st = listed[~listed["name"].str.contains(r"\*?ST", na=False)]
    removed_st = len(listed) - len(not_st)

    from calendar import get_trade_calendar
    from config.params import IPO_LOCK_DAYS

    cal = get_trade_calendar("19900101", trade_date)
    cal_dates = cal["trade_date"].tolist()
    try:
        t_idx = cal_dates.index(trade_date)
    except ValueError:
        logger.warning(f"{trade_date} 非交易日，返回空 universe")
        return not_st.head(0)

    lock_idx = max(0, t_idx - IPO_LOCK_DAYS)
    lock_date = cal_dates[lock_idx]
    filtered = not_st[not_st["list_date"] <= lock_date]
    removed_ipo = len(not_st) - len(filtered)

    logger.info(
        f"universe @ {trade_date}: {len(filtered)} stocks "
        f"(removed: {removed_not_listed} unlisted, "
        f"{removed_st} ST, {removed_ipo} IPO-locked)"
    )
    return filtered[["code", "name"]].reset_index(drop=True)
```

- [ ] **Step 5: 验证 — 测试 3 个日期的 universe**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
from universe import get_universe

for dt in ['20150601', '20190102', '20240102']:
    u = get_universe(dt)
    print(f'{dt}: {len(u)} stocks')
    st_count = u['name'].str.contains(r'\*?ST', na=False).sum()
    assert st_count == 0, f'FAIL: {st_count} ST stocks in universe'
    print(f'  ST check: PASS')
    print(f'  Sample: {u.head(3).values.tolist()}')
"
```

预期: 每期 > 2000 只, 无 ST, 名称正常

- [ ] **Step 6: 提交**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
git add universe.py
git commit -m "feat: add stock universe module with basic filters"
```

---

### Task 4: backtest/engine.py — 等权回测引擎

**Files:**
- Create: `backtest/engine.py`

- [ ] **Step 1: 实现 BacktestResult dataclass**

```python
"""等权回测引擎"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    nav_series: pd.Series       # 每日净值，index=date
    daily_returns: pd.Series    # 日收益率
    trades: pd.DataFrame        # 每笔交易 (date, code, direction, qty, price, cost)
    stats: dict                 # 统计摘要
```

- [ ] **Step 2: 实现 get_open_prices**

```python
import akshare as ak


def get_open_prices(codes: list[str], trade_date: str) -> pd.Series:
    """
    获取指定日期各股票的开盘价。

    对每只股票调用 AKShare 日线，取 trade_date 当天的开盘价。
    批量处理以控制 API 调用次数。

    Args:
        codes: 股票代码列表
        trade_date: 交易日期 "YYYYMMDD"

    Returns:
        Series index=code, value=open_price
    """
    prices = {}
    dt = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"

    for code in codes:
        try:
            hist = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=dt, end_date=dt, adjust="qfq"
            )
            if len(hist) > 0:
                prices[code] = float(hist["开盘"].iloc[0])
        except Exception:
            continue

    return pd.Series(prices, name="open_price")
```

- [ ] **Step 3: 实现 run_backtest 主循环 — 初始化部分**

```python
from loguru import logger

from calendar import get_rebalance_dates, get_t_date, get_trade_calendar
from config.params import (
    INITIAL_CAPITAL, MAX_SINGLE_WEIGHT, MIN_HOLDINGS, TOTAL_COST_RATE,
)
from universe import get_universe


def run_backtest(
    start: str = "20150101",
    end: str = "20241231",
    initial_capital: float = INITIAL_CAPITAL,
) -> BacktestResult:
    """
    等权组合回测主循环。

    Args:
        start: 起始日期 "YYYYMMDD"
        end: 结束日期 "YYYYMMDD"
        initial_capital: 初始资金

    Returns:
        BacktestResult with nav, returns, trades, stats
    """
    rebalance_dates = get_rebalance_dates(start, end)
    trade_cal = get_trade_calendar(start, end)
    all_trade_dates = trade_cal["trade_date"].tolist()

    # 状态变量
    cash = initial_capital
    positions = {}          # code -> shares
    prev_prices = {}        # code -> last close price (for daily NAV)
    trade_records = []
    nav_records = []

    # 追踪调仓周期
    current_target = {}     # code -> target_weight

    logger.info(f"回测 {start} ~ {end}, {len(rebalance_dates)} 个调仓周期")
```

- [ ] **Step 4: 实现 run_backtest 主循环 — 逐日循环**

```python
    rebalance_idx = 0
    prev_day_prices = {}

    for day in all_trade_dates:
        # === 调仓日处理 ===
        if rebalance_idx < len(rebalance_dates) and day == rebalance_dates[rebalance_idx]:
            t_date = get_t_date(day)
            universe = get_universe(t_date)
            codes = universe["code"].tolist()

            if len(codes) == 0:
                logger.warning(f"{day}: universe 为空，跳过调仓")
                rebalance_idx += 1
                continue

            # 等权分配，上限 8%
            n = len(codes)
            raw_weight = 1.0 / n
            weight = min(raw_weight, MAX_SINGLE_WEIGHT)
            target_weights = {c: weight for c in codes}

            # 若 universe < 13，多余资金留现金
            total_allocated = sum(target_weights.values())
            if total_allocated < 1.0:
                cash_float = 1.0 - total_allocated
                # 按持仓数量比例重归一化
                for c in target_weights:
                    target_weights[c] = target_weights[c] / total_allocated

            # 获 target weights 中所有股票的当日开盘价
            open_prices = get_open_prices(list(target_weights.keys()), day)

            # 计算当前持仓市值
            if prev_day_prices:
                current_value = cash
                for c, shares in positions.items():
                    if c in prev_day_prices:
                        current_value += shares * prev_day_prices[c]
            else:
                current_value = initial_capital

            # 卖出不在新目标的持仓
            total_capital = current_value
            for c in list(positions.keys()):
                if c not in target_weights or c not in open_prices:
                    if c in prev_day_prices:
                        sell_price = prev_day_prices[c]
                        cash += positions[c] * sell_price * (1 - TOTAL_COST_RATE)
                        trade_records.append({
                            "date": day, "code": c, "direction": "SELL",
                            "qty": positions[c], "price": sell_price,
                            "cost": positions[c] * sell_price * TOTAL_COST_RATE,
                        })
                    del positions[c]

            # 买入新目标
            total_capital = cash + sum(
                positions.get(c, 0) * (open_prices.get(c) or 0) for c in positions
            )

            for c, w in target_weights.items():
                if c not in open_prices:
                    continue
                target_value = total_capital * w
                current_shares = positions.get(c, 0)
                current_value_c = current_shares * open_prices[c]
                diff_value = target_value - current_value_c

                if diff_value > 0:
                    buy_cost = diff_value * (1 + TOTAL_COST_RATE)
                    shares_to_buy = diff_value / open_prices[c]
                    positions[c] = current_shares + shares_to_buy
                    cash -= buy_cost
                    trade_records.append({
                        "date": day, "code": c, "direction": "BUY",
                        "qty": shares_to_buy, "price": open_prices[c],
                        "cost": diff_value * TOTAL_COST_RATE,
                    })
                elif diff_value < 0:
                    sell_cost = abs(diff_value) * (1 - TOTAL_COST_RATE)
                    shares_to_sell = abs(diff_value) / open_prices[c]
                    positions[c] = max(0, current_shares - shares_to_sell)
                    cash += sell_cost
                    trade_records.append({
                        "date": day, "code": c, "direction": "SELL",
                        "qty": shares_to_sell, "price": open_prices[c],
                        "cost": abs(diff_value) * TOTAL_COST_RATE,
                    })

            # 清理零持仓
            positions = {c: s for c, s in positions.items() if s > 0}

            if len(codes) < MIN_HOLDINGS:
                logger.warning(f"{day}: 仅 {len(codes)} 只标的，低于 {MIN_HOLDINGS} 下限")

            logger.info(
                f"{day}: rebalance t_date={t_date} universe={len(codes)} "
                f"positions={len(positions)} cash={cash:.0f}"
            )
            rebalance_idx += 1

        # === 每日净值计算 ===
        day_prices = {}
        # 尝试获取当日收盘价（用下一日开盘价近似为收盘价，简化处理）
        # 实际中应获取当日收盘价；薄切片阶段用前一交易日已知价格
        if prev_day_prices is None:
            prev_day_prices = {}

        # 用已有价格近似当日净值
        equity = cash
        for c, shares in positions.items():
            # 使用上一已知价格（调仓日已有当日开盘价）
            if c in prev_day_prices:
                equity += shares * prev_day_prices[c]

        nav_records.append({"date": day, "nav": equity})
```

- [ ] **Step 5: 每日净值获取优化 — 调整价格获取策略**

每日获取所有持仓收盘价的开销太大（5000 只股票 × 2400 天）。薄切片改用更务实的方案：

**策略**：只在调仓日获取开盘价，每日净值用前复权收盘价（从 AKShare 预下载沪深300成分股+持仓股的日线，存入本地缓存）。首版用更简单的方法：用 `akshare.stock_zh_a_hist` 批量预下载持仓股历史日线到 `data/cache/daily_prices/`。

调整后的净值计算：

```python
def _load_price_cache(code: str) -> pd.Series:
    """加载单只股票的日线缓存，返回收盘价 Series"""
    cache_path = f"data/cache/daily_prices/{code}.csv"
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, dtype={"date": str})
        df["date"] = df["date"].astype(str)
        return df.set_index("date")["close"]
    # 首次获取
    try:
        hist = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date="20140101", end_date="20251231", adjust="qfq"
        )
        df = hist[["日期", "收盘"]].copy()
        df.columns = ["date", "close"]
        df["date"] = df["date"].str.replace("-", "")
        df["close"] = df["close"].astype(float)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        df.to_csv(cache_path, index=False)
        return df.set_index("date")["close"]
    except Exception:
        return pd.Series(dtype=float)
```

- [ ] **Step 6: 重写 run_backtest — 完整版**

由于上一步改变了价格获取策略，这里给出完整的 run_backtest 函数：

```python
import os

import akshare as ak
import numpy as np
import pandas as pd
from loguru import logger

from calendar import get_rebalance_dates, get_t_date, get_trade_calendar
from config.params import (
    INITIAL_CAPITAL, MAX_SINGLE_WEIGHT, MIN_HOLDINGS, TOTAL_COST_RATE,
)
from universe import get_universe


def _load_price_cache(code: str) -> pd.Series:
    cache_path = f"data/cache/daily_prices/{code}.csv"
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, dtype={"date": str})
        return df.set_index("date")["close"]
    try:
        hist = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date="20140101", end_date="20251231", adjust="qfq"
        )
        df = hist[["日期", "收盘"]].copy()
        df.columns = ["date", "close"]
        df["date"] = df["date"].str.replace("-", "")
        df["close"] = df["close"].astype(float)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        df.to_csv(cache_path, index=False)
        return df.set_index("date")["close"]
    except Exception:
        return pd.Series(dtype=float)


def _get_close_price(code: str, date: str) -> float | None:
    prices = _load_price_cache(code)
    if date in prices.index:
        return float(prices[date])
    # 向前找最近交易日收盘价
    available = prices[prices.index <= date]
    if len(available) > 0:
        return float(available.iloc[-1])
    return None


def run_backtest(
    start: str = "20150101",
    end: str = "20241231",
    initial_capital: float = INITIAL_CAPITAL,
) -> BacktestResult:
    rebalance_dates = get_rebalance_dates(start, end)
    all_trade_dates = get_trade_calendar(start, end)["trade_date"].tolist()

    cash = initial_capital
    positions = {}           # code -> shares
    trade_records = []
    nav_records = []
    rebalance_idx = 0

    logger.info(f"回测 {start} ~ {end}, {len(rebalance_dates)} 调仓周期, {len(all_trade_dates)} 交易日")

    for day in all_trade_dates:
        # --- 调仓 ---
        if rebalance_idx < len(rebalance_dates) and day == rebalance_dates[rebalance_idx]:
            t_date = get_t_date(day)
            universe = get_universe(t_date)
            codes = universe["code"].tolist()

            if len(codes) == 0:
                logger.warning(f"{day}: universe 为空，跳过")
                rebalance_idx += 1
                continue

            n = len(codes)
            raw_w = min(1.0 / n, MAX_SINGLE_WEIGHT)
            target_weights = {c: raw_w for c in codes}

            # 计算当前总资产
            current_equity = cash
            for c, shares in positions.items():
                px = _get_close_price(c, t_date)
                if px is not None:
                    current_equity += shares * px

            # 卖出不在目标的持仓
            for c in list(positions.keys()):
                if c not in target_weights:
                    px = _get_close_price(c, t_date)
                    if px is not None:
                        proceeds = positions[c] * px * (1 - TOTAL_COST_RATE)
                        cash += proceeds
                        trade_records.append({
                            "date": day, "code": c, "direction": "SELL",
                            "qty": positions[c], "price": px,
                            "cost": positions[c] * px * TOTAL_COST_RATE,
                        })
                    del positions[c]

            # 计算调仓后总资产并买入
            total_capital = cash + sum(
                positions.get(c, 0) * (_get_close_price(c, t_date) or 0)
                for c in positions
            )

            for c, w in target_weights.items():
                px = _get_close_price(c, t_date)
                if px is None:
                    continue
                target_value = total_capital * w
                current_shares = positions.get(c, 0)
                diff = target_value - current_shares * px

                if abs(diff) < 1.0:  # 忽略极小调整
                    continue

                shares_diff = diff / px
                if shares_diff > 0:
                    cash -= diff * (1 + TOTAL_COST_RATE)
                    positions[c] = current_shares + shares_diff
                    trade_records.append({
                        "date": day, "code": c, "direction": "BUY",
                        "qty": shares_diff, "price": px,
                        "cost": diff * TOTAL_COST_RATE,
                    })
                else:
                    cash += abs(diff) * (1 - TOTAL_COST_RATE)
                    positions[c] = max(0, current_shares + shares_diff)
                    trade_records.append({
                        "date": day, "code": c, "direction": "SELL",
                        "qty": abs(shares_diff), "price": px,
                        "cost": abs(diff) * TOTAL_COST_RATE,
                    })

            positions = {c: s for c, s in positions.items() if s > 0}
            if len(codes) < MIN_HOLDINGS:
                logger.warning(f"{day}: only {len(codes)} holdings < {MIN_HOLDINGS}")

            logger.info(f"{day}: rebalance t_date={t_date} n={len(codes)} pos={len(positions)}")
            rebalance_idx += 1

        # --- 每日净值 ---
        equity = cash
        for c, shares in positions.items():
            px = _get_close_price(c, day)
            if px is not None:
                equity += shares * px
        nav_records.append({"date": day, "nav": equity})

    # 构建结果
    nav_df = pd.DataFrame(nav_records)
    nav_df["date"] = nav_df["date"].astype(str)
    nav_series = nav_df.set_index("date")["nav"]

    daily_returns = nav_series.pct_change().fillna(0)

    trades_df = pd.DataFrame(trade_records) if trade_records else pd.DataFrame(
        columns=["date", "code", "direction", "qty", "price", "cost"]
    )

    stats = _compute_stats(nav_series, daily_returns)
    return BacktestResult(
        nav_series=nav_series,
        daily_returns=daily_returns,
        trades=trades_df,
        stats=stats,
    )
```

- [ ] **Step 7: 实现 _compute_stats**

```python
def _compute_stats(nav: pd.Series, daily_returns: pd.Series) -> dict:
    """计算绩效统计"""
    trading_days_per_year = 252
    total_days = len(daily_returns)
    years = total_days / trading_days_per_year

    total_return = (nav.iloc[-1] / nav.iloc[0]) - 1
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    annual_vol = daily_returns.std() * np.sqrt(trading_days_per_year)

    risk_free = 0.02  # 2% 无风险利率
    sharpe = (annual_return - risk_free) / annual_vol if annual_vol > 0 else 0

    # 最大回撤
    cummax = nav.cummax()
    drawdown = (nav - cummax) / cummax
    max_drawdown = drawdown.min()

    calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0

    # 胜率（日度）
    win_rate = (daily_returns > 0).sum() / len(daily_returns) if len(daily_returns) > 0 else 0

    # 换手率（年化）
    annual_turnover = 0  # 后续从 trades 计算

    return {
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "annual_volatility": round(annual_vol, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown": round(max_drawdown, 4),
        "calmar_ratio": round(calmar, 4),
        "win_rate": round(win_rate, 4),
        "years": round(years, 2),
        "initial_nav": round(nav.iloc[0], 2),
        "final_nav": round(nav.iloc[-1], 2),
    }
```

- [ ] **Step 8: 提交**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
git add backtest/ backtest/engine.py
git commit -m "feat: add equal-weight backtest engine with daily NAV tracking"
```

---

### Task 5: main.py 入口 + 集成跑通

**Files:**
- Create: `main.py`

- [ ] **Step 1: 写入 main.py**

```python
"""周期驱动因子系统 — 主入口"""
import os

import pandas as pd

from backtest.engine import run_backtest
from config.params import OUTPUT_DIR


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    result = run_backtest("20150101", "20241231")

    stats = result.stats
    print("\n=== 回测统计 ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    nav_path = os.path.join(OUTPUT_DIR, "nav.csv")
    result.nav_series.to_csv(nav_path, header=["nav"])
    print(f"\n净值序列已保存至 {nav_path}")

    trades_path = os.path.join(OUTPUT_DIR, "trades.csv")
    result.trades.to_csv(trades_path, index=False)
    print(f"交易记录已保存至 {trades_path}")

    # 基准对比：输出年化收益与最大回撤
    print(f"\n年化收益: {stats['annual_return']:.2%}")
    print(f"年化波动: {stats['annual_volatility']:.2%}")
    print(f"夏普比率: {stats['sharpe_ratio']:.2f}")
    print(f"最大回撤: {stats['max_drawdown']:.2%}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行回测**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python main.py
```

预期输出: 10 年回测运行成功，输出净值 CSV 和统计摘要

- [ ] **Step 3: 验证输出**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
import pandas as pd

nav = pd.read_csv('output/nav.csv')
print(f'交易天数: {len(nav)}')
print(f'初始净值: {nav.iloc[0].values[0]:.2f}')
print(f'最终净值: {nav.iloc[-1].values[0]:.2f}')
print(f'日均收益: {nav.pct_change().mean().values[0]:.6f}')

# 验证净值 > 0（没爆仓）
assert nav.iloc[-1].values[0] > 0, '净值归零!'

trades = pd.read_csv('output/trades.csv')
print(f'总交易笔数: {len(trades)}')
print(f'买入: {(trades.direction==\"BUY\").sum()}, 卖出: {(trades.direction==\"SELL\").sum()}')
"
```

预期: 净值 > 0, 交易笔数 > 0

- [ ] **Step 4: 提交**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
git add main.py output/
git commit -m "feat: add main entry point, complete Slice 1 backtest pipeline"
```

---

## 成功标准对照

| 标准 | 验证方式 |
|------|---------|
| 获取 2015-2024 交易日历无间断 | Task 2 Step 4: len(cal) > 2400 |
| universe 返回 > 2000 只, 无 ST | Task 3 Step 5: assert |
| 回测 10 年无异常, 输出 CSV | Task 5 Step 3: nav.csv + trades.csv |
| 年化换手率 < 500% | 从 trades 计算（Task 5 Step 3 后手动检查） |
| 夏普/回撤在合理范围 | 与沪深300基准对比（手动验证） |
