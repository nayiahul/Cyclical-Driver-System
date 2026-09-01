"""Confirmation Engine Audit v1 — 市场层因子有效性检验（PIT 后）。

回答: 修复后 Confirmation Engine 的真实价值。
对每个采样调仓日:
  - 全量候选按 RPS60 分组 → 未来 1/3/6 月收益
  - 检验 RPS 单调性 (Q1高RPS vs Q10低RPS)
  - 同法检验 行业动量 / PE分位

输入: B1 状态（价格 PIT + 规则恢复），因子用 _MARKET.as_of 计算（天然 PIT）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from trade_calendar import get_t_date, get_rebalance_dates
from universe import get_universe
from industry import get_sw_industry
from valuation_filter import apply_valuation_filter
from screener import compute_rps60, compute_industry_momentum
from pit.market import MarketData

STOCKS_DIR = "/Users/nayiahlu/Desktop/stocks"
mkt = MarketData()

def fwd_ret(code, day, months, all_reb):
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

def main():
    all_reb = get_rebalance_dates("20220101", "20251231")
    sampled = [d for i, d in enumerate(all_reb) if i % 3 == 0][:8]  # 8 季度采样
    
    rows = []
    for day in sampled:
        t_date = get_t_date(day)
        u = get_universe(t_date)
        ind = get_sw_industry()
        codes = apply_valuation_filter(t_date, u["code"].tolist(), ind)
        rps = compute_rps60(codes, t_date, ind)
        ind_mom = compute_industry_momentum(codes, t_date, ind)
        for c in codes[:800]:  # 采样控制成本
            if c not in rps:
                continue
            rows.append({
                "day": day, "code": c,
                "rps": rps.get(c, np.nan),
                "ind_mom": ind_mom.get(c, np.nan),
                "fwd1": fwd_ret(c, day, 1, all_reb),
                "fwd3": fwd_ret(c, day, 3, all_reb),
                "fwd6": fwd_ret(c, day, 6, all_reb),
            })
        print(f"{day}: {len([r for r in rows if r['day']==day])} 行", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv("baseline/confirmation_audit.csv", index=False)
    print(f"saved {len(df)} rows", flush=True)

if __name__ == "__main__":
    main()
