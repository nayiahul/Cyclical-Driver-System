# Slice 3: Alpha 信号层 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用 4 个 Alpha 信号（S3动量+S4行业+S5盈利+S7现金流）精选 Top100 股票，等权配置，验证 Alpha 能否跑赢全市场等权基准

**Architecture:** 新增 `industry.py`（SW行业映射）+ `signals.py`（4信号+Alpha合成），修改 `engine.py`（全市场等权→Top100等权）。信号在申万一级行业内做 Z-Score，NaN 不淘汰只跳过，Alpha = 非NaN因子等权均值

**Tech Stack:** Python 3.10, pandas, numpy, akshare, loguru

---

## 文件结构映射

| 文件 | 职责 | 数据依赖 |
|------|------|---------|
| `config/params.py` | 信号阈值（RPS65, TopN100, 行业占比阈值等） | 无 |
| `industry.py` | code → 申万一级行业映射 | AKShare `index_stock_cons` |
| `signals.py` | S3/S4/S5/S7 + Alpha合成 | industry, daily_prices, AKShare financial |
| `backtest/engine.py` | 全市场等权 → Top100 Alpha等权 | signals, universe |

依赖链: params → industry → signals → engine，单向无循环。

---

### Task 1: 更新 config/params.py — 信号阈值

**Files:**
- Modify: `config/params.py`

- [ ] **Step 1: 追加信号阈值常量**

在文件末尾追加：

```python
# ============================================================
# Alpha 信号阈值
# ============================================================

# S3 个股动量
RPS60_MIN = 65              # RPS60最低百分位
MOMENTUM_DAYS_ABOVE_MA = 30 # 60日中收盘>MA50的最少天数

# S4 行业趋势共振
SECTOR_TOP_PCT = 0.40       # 行业涨幅排名前40%
SECTOR_BREADTH_MIN = 0.50   # 行业内上涨占比下限
SECTOR_NEWHIGH_LOOKBACK = 5 # 行业新高占比对比年限

# Alpha 合成
TOP_N_STOCKS = 100           # 入选股票数
MAX_SINGLE_WEIGHT = 0.08     # 单票上限8%（沿用已有）

# 财务数据
FIN_START_YEAR = 2012        # 财务数据起始年份(2015-3=2012)
ROE_MIN_QUARTERS = 8         # ROE最少季度数
```

- [ ] **Step 2: 验证导入**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "from config.params import RPS60_MIN, TOP_N_STOCKS, FIN_START_YEAR; print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add config/params.py
git commit -m "feat: add alpha signal thresholds config"
```

---

### Task 2: 创建 industry.py — 申万行业映射

**Files:**
- Create: `industry.py`

- [ ] **Step 1: 实现 get_sw_industry**

```python
"""申万2024一级行业映射"""
import os

import akshare as ak
import pandas as pd
from loguru import logger

SW_INDUSTRY_CACHE = "data/cache/sw_industry_map.csv"

# 申万2021版 31个一级行业指数代码
SW_CODES = {
    "801010": "农林牧渔", "801020": "煤炭", "801030": "化工",
    "801040": "钢铁", "801050": "有色金属", "801080": "电子",
    "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服饰",
    "801140": "轻工制造", "801150": "医药生物", "801160": "公用事业",
    "801170": "交通运输", "801180": "房地产", "801200": "商贸零售",
    "801210": "社会服务", "801230": "综合", "801710": "建筑材料",
    "801720": "建筑装饰", "801730": "电力设备", "801740": "国防军工",
    "801750": "计算机", "801760": "传媒", "801770": "通信",
    "801780": "银行", "801790": "非银金融", "801880": "汽车",
    "801890": "机械设备", "801960": "石油石化", "801970": "环保",
    "801980": "美容护理",
}


def get_sw_industry() -> dict[str, str]:
    """
    返回 {stock_code: sw_industry_name} 映射。

    缓存优先。首次调用遍历31个申万行业指数获取成分股。
    若某股票出现在多个行业中，取首次匹配的行业。
    """
    if os.path.exists(SW_INDUSTRY_CACHE):
        df = pd.read_csv(SW_INDUSTRY_CACHE, dtype={"code": str, "industry": str})
        return dict(zip(df["code"], df["industry"]))

    mapping: dict[str, str] = {}
    for sw_code, industry_name in SW_CODES.items():
        try:
            df = ak.index_stock_cons(symbol=sw_code)
            for _, row in df.iterrows():
                code = str(row["品种代码"]).zfill(6)
                if code not in mapping:
                    mapping[code] = industry_name
            logger.debug(f"{industry_name}({sw_code}): {len(df)} stocks")
        except Exception as e:
            logger.warning(f"获取 {industry_name}({sw_code}) 成分股失败: {e}")

    # 保存缓存
    cache_df = pd.DataFrame(
        [{"code": k, "industry": v} for k, v in mapping.items()]
    )
    os.makedirs(os.path.dirname(SW_INDUSTRY_CACHE), exist_ok=True)
    cache_df.to_csv(SW_INDUSTRY_CACHE, index=False)
    logger.info(f"申万行业映射已缓存: {len(mapping)} 只股票, {len(SW_CODES)} 个行业")
    return mapping
```

- [ ] **Step 2: 验证 — 测试映射覆盖**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
from industry import get_sw_industry
m = get_sw_industry()
print(f'Total stocks: {len(m)}')
# Check coverage: how many universe stocks have industry?
from universe import get_stock_list
stocks = get_stock_list()
covered = sum(1 for c in stocks['code'] if c in m)
print(f'Universe coverage: {covered}/{len(stocks)} ({covered/len(stocks)*100:.0f}%)')
# Show industry distribution
from collections import Counter
ic = Counter(m.values())
for ind, cnt in ic.most_common(5):
    print(f'  {ind}: {cnt}')
"
```

预期: > 4000 股票覆盖，31 个行业全有点

- [ ] **Step 3: 提交**

```bash
git add industry.py data/cache/sw_industry_map.csv
git commit -m "feat: add Shenwan industry mapping module"
```

---

### Task 3: 创建 signals.py — 完整信号计算

**Files:**
- Create: `signals.py`

- [ ] **Step 1: 实现财务数据加载器 + S5 + S7**

```python
"""Alpha信号计算：S3(动量) S4(行业共振) S5(盈利稳定性) S7(现金流质量)"""
import os
from collections import defaultdict

import akshare as ak
import numpy as np
import pandas as pd
from loguru import logger

from config.params import (
    FIN_START_YEAR, MOMENTUM_DAYS_ABOVE_MA, ROE_MIN_QUARTERS,
    RPS60_MIN, SECTOR_BREADTH_MIN, SECTOR_NEWHIGH_LOOKBACK, SECTOR_TOP_PCT,
)
from industry import get_sw_industry
from trade_calendar import get_trade_calendar

FIN_CACHE = "data/cache/financial_data.csv"


def _load_price_data(code: str) -> pd.DataFrame:
    """加载个股日线缓存"""
    path = f"data/cache/daily_prices/{code}.csv"
    if os.path.exists(path):
        df = pd.read_csv(path, dtype={"date": str})
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()
    return pd.DataFrame()


def _load_financial_data() -> pd.DataFrame:
    """
    加载财务数据缓存。首次调用遍历全部A股获取财务指标。
    缓存到 data/cache/financial_data.csv。
    
    Columns: code, date, roe_weighted, ocf_to_revenue
    """
    if os.path.exists(FIN_CACHE):
        return pd.read_csv(FIN_CACHE, dtype={"code": str})

    from universe import get_stock_list
    stocks = get_stock_list()
    codes = stocks["code"].tolist()

    records = []
    for i, code in enumerate(codes):
        try:
            df = ak.stock_financial_analysis_indicator(
                symbol=code, start_year=str(FIN_START_YEAR)
            )
            for _, row in df.iterrows():
                records.append({
                    "code": code,
                    "date": str(row["日期"])[:10],
                    "roe_weighted": float(row.get("加权净资产收益率(%)", np.nan) or np.nan),
                    "ocf_to_revenue": float(
                        row.get("经营现金净流量对销售收入比率(%)", np.nan) or np.nan
                    ),
                })
        except Exception:
            continue
        if (i + 1) % 500 == 0:
            logger.info(f"财务数据进度: {i+1}/{len(codes)}")

    df = pd.DataFrame(records)
    os.makedirs(os.path.dirname(FIN_CACHE), exist_ok=True)
    df.to_csv(FIN_CACHE, index=False)
    logger.info(f"财务数据已缓存: {len(df)} 条记录, {df['code'].nunique()} 只股票")
    return df


def _zscore(series: pd.Series) -> pd.Series:
    """Z-Score标准化，缩尾1%/99%"""
    lo, hi = series.quantile(0.01), series.quantile(0.99)
    clipped = series.clip(lo, hi)
    mu, sigma = clipped.mean(), clipped.std()
    if sigma == 0:
        return pd.Series(0.0, index=series.index)
    return (clipped - mu) / sigma


def compute_S3(t_date: str, codes: list[str], industry_map: dict[str, str]) -> pd.Series:
    """
    S3 个股动量。

    5项条件全部满足 → RPS60的行业内Z-Score；否则NaN。
    """
    scores = {}
    # 获取 t_date 之前60个交易日范围
    cal = get_trade_calendar("20140101", t_date)
    all_dates = cal["trade_date"].tolist()
    if len(all_dates) < 200:
        return pd.Series(dtype=float)

    t_idx = all_dates.index(t_date) if t_date in all_dates else len(all_dates) - 1
    # 60日前
    start_idx = max(0, t_idx - 60)
    date_60d_ago = all_dates[start_idx]
    date_200d_ago = all_dates[max(0, t_idx - 200)]

    # 按行业分组计算RPS60
    industry_returns = defaultdict(list)
    code_data = {}

    for code in codes:
        df = _load_price_data(code)
        if len(df) < 200:
            continue
        df = df[(df.index >= date_200d_ago) & (df.index <= all_dates[t_idx])]
        if len(df) < 200:
            continue

        close = df["close"]
        # RPS60
        price_60d_ago = close[close.index <= date_60d_ago]
        if len(price_60d_ago) == 0:
            continue
        ret_60d = close.iloc[-1] / price_60d_ago.iloc[-1] - 1

        # MA50, MA200
        ma50 = close.rolling(50).mean().iloc[-1]
        ma200 = close.rolling(200).mean().iloc[-1]
        last_close = close.iloc[-1]

        # 条件2: close > MA50
        cond2 = last_close > ma50
        # 条件3: MA50 > MA200
        cond3 = ma50 > ma200

        # 条件4: 振幅 < 90%分位
        if "high" in df.columns and "low" in df.columns:
            amplitude = (df["high"] - df["low"]) / df["close"]
            amp_30d = amplitude.iloc[-30:].mean()
            amp_90pct = amplitude.quantile(0.9)
            cond4 = amp_30d < amp_90pct
        else:
            cond4 = True  # 缺少高低价数据则跳过此条件

        # 条件5: 60日中有>=30日 close > MA50
        above_ma50 = (close > close.rolling(50).mean()).iloc[-60:].sum()
        cond5 = above_ma50 >= MOMENTUM_DAYS_ABOVE_MA

        if not (cond2 and cond3 and cond4 and cond5):
            continue

        ind = industry_map.get(code, "未知")
        code_data[code] = {"ret_60d": ret_60d, "industry": ind}
        industry_returns[ind].append((code, ret_60d))

    # 条件1: RPS60 >= 65 (行业内百分位)
    for ind, items in industry_returns.items():
        rets = [r for _, r in items]
        if len(rets) < 10:
            continue
        for code, ret in items:
            pct = sum(1 for r in rets if r <= ret) / len(rets) * 100
            if pct >= RPS60_MIN:
                scores[code] = ret

    if not scores:
        return pd.Series(dtype=float)

    result = pd.Series(scores)
    # 行业内Z-Score
    zscored = result.groupby(
        lambda c: industry_map.get(c, "未知")
    ).transform(_zscore)
    return zscored


def compute_S4(t_date: str, codes: list[str], industry_map: dict[str, str]) -> pd.Series:
    """
    S4 行业趋势共振。

    三个条件全部满足 → 0.7×Z(行业涨幅) + 0.3×Z(行业广度)。
    不满足的行业内所有股票S4=NaN。
    """
    cal = get_trade_calendar("20140101", t_date)
    all_dates = cal["trade_date"].tolist()
    if len(all_dates) < 250:
        return pd.Series(dtype=float)

    t_idx = all_dates.index(t_date) if t_date in all_dates else len(all_dates) - 1
    date_60d_ago = all_dates[max(0, t_idx - 60)]
    date_250d_ago = all_dates[max(0, t_idx - 250)]
    date_20d_ago = all_dates[max(0, t_idx - 20)]

    # 按行业聚合
    ind_codes = defaultdict(list)
    for c in codes:
        ind_codes[industry_map.get(c, "未知")].append(c)

    industry_stats = {}
    for ind, ind_cs in ind_codes.items():
        rets_60d = []
        rets_20d = []
        near_high_count = 0
        total = 0

        for code in ind_cs:
            df = _load_price_data(code)
            if len(df) < 250:
                continue
            df = df[(df.index >= date_250d_ago) & (df.index <= all_dates[t_idx])]
            if len(df) < 60:
                continue
            close = df["close"]
            total += 1

            # 60日收益
            p60 = close[close.index <= date_60d_ago]
            if len(p60) > 0:
                rets_60d.append(close.iloc[-1] / p60.iloc[-1] - 1)

            # 20日收益（广度判断）
            p20 = close[close.index <= date_20d_ago]
            if len(p20) > 0:
                ret_20d = close.iloc[-1] / p20.iloc[-1] - 1
                rets_20d.append(ret_20d)

            # 距52周高点
            high_250 = close.rolling(250).max().iloc[-1]
            if (high_250 - close.iloc[-1]) / high_250 < 0.05:
                near_high_count += 1

        if total < 5:
            continue

        med_ret_60d = np.median(rets_60d) if rets_60d else 0
        breadth = sum(1 for r in rets_20d if r > 0) / len(rets_20d) if rets_20d else 0
        new_high_pct = near_high_count / total

        industry_stats[ind] = {
            "ret_60d": med_ret_60d,
            "breadth": breadth,
            "new_high_pct": new_high_pct,
            "total": total,
        }

    # 计算各行业历史新高占比中位数（用于条件3对比）
    # 简化：用当前所有行业的新高占比分布代替5年历史
    all_new_high = [s["new_high_pct"] for s in industry_stats.values()]
    median_nh = np.median(all_new_high) if all_new_high else 0

    # 条件1: 行业涨幅排名前40%
    rets = [(ind, s["ret_60d"]) for ind, s in industry_stats.items()]
    rets.sort(key=lambda x: x[1], reverse=True)
    n_top = max(1, int(len(rets) * SECTOR_TOP_PCT))
    top_industries = {ind for ind, _ in rets[:n_top]}

    # 有效行业的S4分数
    sector_scores = {}
    for ind, s in industry_stats.items():
        cond1 = ind in top_industries
        cond2 = s["breadth"] > SECTOR_BREADTH_MIN
        cond3 = s["new_high_pct"] > median_nh

        if cond1 and cond2 and cond3:
            sector_scores[ind] = 0.7 * s["ret_60d"] + 0.3 * s["breadth"]

    if not sector_scores:
        return pd.Series(dtype=float)

    # 行业分数做Z-Score
    s4_raw = pd.Series(sector_scores)
    s4_z = _zscore(s4_raw)

    # 分配给行业内每只股票
    result = {}
    for ind, z in s4_z.items():
        for code in ind_codes.get(ind, []):
            result[code] = z

    return pd.Series(result)


def compute_S5(t_date: str, codes: list[str], industry_map: dict[str, str]) -> pd.Series:
    """
    S5 盈利稳定性。

    近3年（12季度）加权ROE标准差，行业内反向Z-Score。
    """
    fin = _load_financial_data()
    fin["date"] = pd.to_datetime(fin["date"])
    cutoff = pd.to_datetime(t_date, format="%Y%m%d")
    fin = fin[fin["date"] <= cutoff]

    roe_std = {}
    for code in codes:
        code_fin = fin[fin["code"] == code]
        if len(code_fin) < ROE_MIN_QUARTERS:
            continue
        roe = code_fin["roe_weighted"].dropna()
        if len(roe) < ROE_MIN_QUARTERS:
            continue
        roe_std[code] = roe.tail(12).std()

    if not roe_std:
        return pd.Series(dtype=float)

    result = pd.Series(roe_std)
    # 行业内反向Z-Score（标准差越小越好）
    grouped = result.groupby(lambda c: industry_map.get(c, "未知"))
    zscored = grouped.transform(lambda x: -_zscore(x))
    return zscored


def compute_S7(t_date: str, codes: list[str], industry_map: dict[str, str]) -> pd.Series:
    """
    S7 现金流质量。

    最新季度经营现金流/营收，行业内Z-Score。负值→NaN。
    """
    fin = _load_financial_data()
    fin["date"] = pd.to_datetime(fin["date"])
    cutoff = pd.to_datetime(t_date, format="%Y%m%d")
    fin = fin[fin["date"] <= cutoff]

    ocf_ratio = {}
    for code in codes:
        code_fin = fin[fin["code"] == code]
        ocf = code_fin["ocf_to_revenue"].dropna()
        if len(ocf) == 0:
            continue
        latest = ocf.iloc[-1]
        if latest > 0:
            ocf_ratio[code] = latest

    if not ocf_ratio:
        return pd.Series(dtype=float)

    result = pd.Series(ocf_ratio)
    grouped = result.groupby(lambda c: industry_map.get(c, "未知"))
    zscored = grouped.transform(_zscore)
    return zscored


def compute_alpha(t_date: str, codes: list[str]) -> dict[str, float]:
    """
    合成Alpha Score。

    Alpha = S3/S4/S5/S7中非NaN值的等权平均。
    行业映射在所有信号间共享。
    财务数据首次调用时下载（可能较慢）。
    """
    industry_map = get_sw_industry()

    s3 = compute_S3(t_date, codes, industry_map)
    s4 = compute_S4(t_date, codes, industry_map)
    s5 = compute_S5(t_date, codes, industry_map)
    s7 = compute_S7(t_date, codes, industry_map)

    logger.info(
        f"S3有效: {s3.notna().sum()}/{len(codes)}, "
        f"S4有效: {s4.notna().sum()}/{len(codes)}, "
        f"S5有效: {s5.notna().sum()}/{len(codes)}, "
        f"S7有效: {s7.notna().sum()}/{len(codes)}"
    )

    alpha = {}
    for code in codes:
        vals = []
        for s in [s3, s4, s5, s7]:
            if code in s.index and not pd.isna(s[code]):
                vals.append(s[code])
        if vals:
            alpha[code] = sum(vals) / len(vals)

    return alpha
```

- [ ] **Step 2: 验证 — 测试各信号函数**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
from universe import get_universe
from trade_calendar import get_t_date
from signals import compute_alpha

# 测试单个日期的Alpha计算
t_date = '20240131'
u = get_universe(t_date)
codes = u['code'].tolist()[:200]  # 先用200只测试
print(f'Testing with {len(codes)} stocks...')

alpha = compute_alpha(t_date, codes)
print(f'Alpha scores: {len(alpha)} stocks')
if alpha:
    top = sorted(alpha.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f'Top5: {top}')
print('OK')
"
```

预期: 各信号有合理输出比例，Alpha 得分有区分度。

注意：首次运行 `_load_financial_data` 会遍历全部 A 股下载财务数据（约 5000 次 API 调用），预计耗时较长（30-60 分钟）。后续从缓存读取。

- [ ] **Step 3: 提交**

```bash
git add signals.py data/cache/financial_data.csv
git commit -m "feat: add 4-factor alpha signals (S3 momentum, S4 sector, S5 stability, S7 cashflow)"
```

---

### Task 4: 修改 engine.py — Top100 Alpha 选股

**Files:**
- Modify: `backtest/engine.py`

- [ ] **Step 1: 修改 imports 和调仓逻辑**

在 `backtest/engine.py` 中添加导入：

```python
from config.params import (
    END_DATE,
    INITIAL_CAPITAL,
    MAX_SINGLE_WEIGHT,
    MIN_HOLDINGS,
    START_DATE,
    TOP_N_STOCKS,
    TOTAL_COST_RATE,
)
from signals import compute_alpha
```

找到调仓逻辑中的权重计算部分，将：

```python
                target_weights = {
                    code: min(1.0 / n, MAX_SINGLE_WEIGHT)
                    for code in target_codes
                }
```

改为：

```python
                # Alpha选股: Top N
                alpha_scores = compute_alpha(t_date, target_codes)
                ranked = sorted(
                    alpha_scores.items(), key=lambda x: x[1], reverse=True
                )
                selected = [c for c, _ in ranked[:TOP_N_STOCKS]]
                n_selected = len(selected)

                if n_selected < MIN_HOLDINGS:
                    logger.warning(
                        f"{day}: Alpha选股仅{n_selected}只, 低于{MIN_HOLDINGS}下限"
                    )

                # 等权分配，单票上限8%
                weight = min(1.0 / max(n_selected, 1), MAX_SINGLE_WEIGHT)
                target_weights = {c: weight for c in selected}
```

同时移除 Slice 2 的 Regime 仓位缩放代码（`position_cap` 相关行）和 `detect_regime` 调用。

- [ ] **Step 2: 验证导入**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "from backtest.engine import run_backtest; print('engine imports OK')"
```

- [ ] **Step 3: 提交**

```bash
git add backtest/engine.py
git commit -m "feat: switch from market equal-weight to Top100 Alpha selection"
```

---

### Task 5: 回测 + 对比

**Files:**
- 无新建文件

- [ ] **Step 1: 运行 Slice 3 回测**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
import os
from backtest.engine import run_backtest

result = run_backtest('20150101', '20241231')
stats = result.stats
print()
print('=== Slice 3 回测统计 (Top100 Alpha等权) ===')
for k, v in stats.items():
    print(f'  {k}: {v}')

os.makedirs('output', exist_ok=True)
result.nav_series.to_csv('output/nav_slice3.csv', header=['nav'])
result.trades.to_csv('output/trades_slice3.csv', index=False)
print()
print('已保存至 output/nav_slice3.csv')
"
```

注意：首次运行需下载财务数据和 Alpha 计算，预计耗时较长。

- [ ] **Step 2: 三版本对比**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
import pandas as pd
import numpy as np

def calc_stats(nav_path):
    nav = pd.read_csv(nav_path, index_col=0).iloc[:, 0]
    ret = nav.pct_change().dropna()
    years = len(ret) / 252
    total = (nav.iloc[-1] / nav.iloc[0]) - 1
    ann = (1 + total) ** (1/years) - 1 if years > 0 else 0
    vol = ret.std() * np.sqrt(252)
    sharpe = (ann - 0.02) / vol if vol > 0 else 0
    cummax = nav.cummax()
    mdd = ((nav - cummax) / cummax).min()
    return ann, vol, sharpe, mdd, total

versions = {
    'Slice 1 (等权全市场)': 'output/nav.csv',
    'Slice 2 (周期仓位)': 'output/nav_slice2.csv',
    'Slice 3 (Top100 Alpha)': 'output/nav_slice3.csv',
}

print(f'{'版本':<25} {'年化收益':>8} {'波动':>8} {'夏普':>6} {'最大回撤':>10} {'累计收益':>10}')
print('-' * 70)
for name, path in versions.items():
    try:
        ann, vol, sharpe, mdd, total = calc_stats(path)
        print(f'{name:<25} {ann:>7.2%} {vol:>7.2%} {sharpe:>5.2f} {mdd:>9.2%} {total:>9.2%}')
    except Exception as e:
        print(f'{name:<25} (数据不可用: {e})')
"
```

- [ ] **Step 3: 提交最终结果**

```bash
git add output/
git commit -m "feat: complete Slice 3 backtest with Top100 Alpha selection"
```

---

## 成功标准对照

| 标准 | 验证方式 |
|------|---------|
| industry.py 覆盖 > 4000 只股票 | Task 2 Step 2 |
| 每个信号独立可运行 | Task 3 Step 2 |
| S3 约10-15%有效(动量精选) | Task 3 Step 2 日志 |
| S4 约30-40%有效(行业共振) | Task 3 Step 2 日志 |
| 回测无异常，Top100 ≥ 15只 | Task 5 Step 1 |
| 夏普/回撤 vs Slice 1 有改善 | Task 5 Step 2 |
