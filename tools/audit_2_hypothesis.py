"""Baseline A Audit 2/2: 生命周期分布 + 认知差初步验证（采样12个季度调仓日）

对每个采样日: universe → valuation → RPS/S1/S2 → 当日 Top100 三维状态
→ 未来 1/3/6 月收益 → 认知差分组 (Early Discovery vs Confirmed vs No-Change)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from trade_calendar import get_t_date, get_rebalance_dates
from universe import get_universe
from industry import get_sw_industry
from valuation_filter import apply_valuation_filter
from screener import compute_rps60
from signals import compute_S1, compute_S2
from config.params import STOCKS_DIR, TOP_N_STOCKS

# 采样: 每季度首月调仓日 (2022Q1..2025Q4)
all_reb = get_rebalance_dates("20220101", "20251231")
sampled = [d for i, d in enumerate(all_reb) if i % 3 == 0][:12]

# trades 实际买入
trades = pd.read_csv("baseline/pre_pit_A/trades.csv", dtype={"code": str, "date": str})
trades["code"] = trades["code"].str.zfill(6)
buys = trades[trades["direction"] == "buy"]

def fwd_ret(code, day, months):
    """未来 months 月收益 (t 后第 months 个调仓日)"""
    idx = all_reb.index(day)
    target = all_reb[min(idx + months, len(all_reb) - 1)]
    path = os.path.join(STOCKS_DIR, f"{code}.csv")
    if not os.path.exists(path):
        return np.nan
    df = pd.read_csv(path, dtype={"date": str})
    df["date"] = df["date"].str.replace("-", "", regex=False)
    d1 = df[df["date"] <= day]
    d2 = df[df["date"] <= target]
    if len(d1) == 0 or len(d2) == 0:
        return np.nan
    p1 = float(d1["close"].iloc[-1]); p2 = float(d2["close"].iloc[-1])
    return p2 / p1 - 1 if p1 > 0 else np.nan

rows = []
for day in sampled:
    t_date = get_t_date(day)
    u = get_universe(t_date)
    ind = get_sw_industry()
    codes = apply_valuation_filter(t_date, u["code"].tolist(), ind)
    rps = compute_rps60(codes, t_date, ind)
    s1 = compute_S1(t_date, codes, ind)
    s2 = compute_S2(t_date, codes, ind)
    # 当日实际买入 (Top100)
    day_buys = buys[buys["date"] == day]["code"].tolist()
    for c in day_buys:
        r = rps.get(c, np.nan)
        s1v = s1.get(c, np.nan) if c in s1.index else np.nan
        s2v = s2.get(c, np.nan) if c in s2.index else np.nan
        rows.append({
            "day": day, "code": c,
            "rps": r, "s1": s1v, "s2": s2v,
            "fwd1": fwd_ret(c, day, 1),
            "fwd3": fwd_ret(c, day, 3),
            "fwd6": fwd_ret(c, day, 6),
        })
    print(f"{day}: {len(day_buys)} 买入, RPS覆盖 {sum(1 for c in day_buys if c in rps)}", flush=True)

df = pd.DataFrame(rows)
df.to_csv("baseline/pre_pit_A/hypothesis_samples.csv", index=False)
print(f"saved {len(df)} rows", flush=True)
