"""Discovery Signal Audit v1 — 探针信号 vs RPS 的正交性检验。

回答三个问题:
  E1: 探针单变量是否有预测力? (green vs red 未来收益)
  E2: Discovery × RPS 二维矩阵 (核心: Discovery High + RPS Low 组表现)
  E3: 覆盖率 (探针在候选池中的可用比例)

设计:
  - B 状态 (PIT 后): RPS 用 _MARKET.as_of, 财务用披露日治理
  - 6 个季度调仓日采样 × 全候选池
  - 探针 1-3 (订单领先/CAPEX效率/毛利韧性); 探针 4 (PDF) 单独评估
  - 性能: 预热 growth_os.data._quarterly_cache (一次 filter + groupby),
    探针调用全部命中缓存

输出: baseline/discovery_audit.csv + 分组统计
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
from pit.market import MarketData
import growth_os.data as gdata
from growth_os.growth_probes import (
    probe_order_leadership, probe_capex_efficiency, probe_margin_resilience,
)
from data_governance import filter_available_reports, load_tdx_raw
from config.params import STOCKS_DIR

STOCKS_DIR = os.path.expanduser("~/Desktop/stocks")
mkt = MarketData()
LEVEL_SCORE = {"green": 1.0, "yellow": 0.5, "red": 0.0, "unknown": np.nan}
FIELDS = ["contract_liabilities", "revenue_yoy", "capex_cash", "roic",
          "gross_margin"]


def prewarm_cache(t_date: str):
    """一次 filter + groupby, 预热 _quarterly_cache (探针全部命中)。"""
    raw = load_tdx_raw()
    avail = filter_available_reports(raw, t_date)
    avail["code"] = avail["code"].astype(str).str.zfill(6)
    gdata._snapshot_cache[t_date] = (
        avail.sort_values("report_date_str").groupby("code").tail(1).copy()
    )
    for code, g in avail.groupby("code"):
        gs = g.sort_values("report_date_str")
        for f in FIELDS:
            if f in gs.columns:
                gdata._quarterly_cache[(code, f, t_date)] = (
                    gs.set_index("report_date_str")[f].astype(float)
                )


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
    sampled = [d for i, d in enumerate(all_reb) if i % 4 == 0][:6]
    rows = []
    for day in sampled:
        t_date = get_t_date(day)
        u = get_universe(t_date)
        ind = get_sw_industry()
        codes = apply_valuation_filter(t_date, u["code"].tolist(), ind)
        prewarm_cache(t_date)
        rps = compute_rps60(codes, t_date, ind)

        for c in codes:
            p1 = probe_order_leadership(c, t_date)
            p2 = probe_capex_efficiency(c, t_date)
            p3 = probe_margin_resilience(c, t_date)
            levels = [p1["level"], p2["level"], p3["level"]]
            scores = [LEVEL_SCORE.get(l, np.nan) for l in levels]
            disc = np.nanmean(scores) if any(not np.isnan(s) for s in scores) else np.nan
            rows.append({
                "day": day, "code": c,
                "rps": rps.get(c, np.nan),
                "order": LEVEL_SCORE.get(p1["level"], np.nan),
                "capex": LEVEL_SCORE.get(p2["level"], np.nan),
                "margin": LEVEL_SCORE.get(p3["level"], np.nan),
                "discovery": disc,
                "fwd1": fwd_ret(c, day, 1, all_reb),
                "fwd3": fwd_ret(c, day, 3, all_reb),
                "fwd6": fwd_ret(c, day, 6, all_reb),
            })
        print(f"{day}: {len(codes)} 候选, 完成", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv("baseline/discovery_audit.csv", index=False)
    print(f"saved {len(df)} rows", flush=True)

    # ============ E1: 单变量 ============
    print("\n=== E1: 探针单变量未来 6 月收益 ===")
    for probe in ["order", "capex", "margin", "discovery"]:
        groups = {}
        for lev in [1.0, 0.5, 0.0]:
            g = df[(df[probe] == lev) & df["fwd6"].notna()]
            if len(g) > 30:
                groups[f"{lev:.1f}"] = g["fwd6"].mean()
        if groups:
            print(f"  {probe:<8} " + " | ".join(f"{k}: {v:>6.1%}" for k, v in sorted(groups.items(), reverse=True)))

    # ============ E2: Discovery × RPS 矩阵 ============
    print("\n=== E2: Discovery × RPS 未来 6 月收益矩阵 ===")
    d = df.dropna(subset=["discovery", "rps", "fwd6"]).copy()
    d["disc_q"] = pd.qcut(d["discovery"], 3, labels=["低", "中", "高"])
    d["rps_q"] = pd.qcut(d["rps"], 3, labels=["低", "中", "高"])
    pivot = d.pivot_table(index="disc_q", columns="rps_q", values="fwd6",
                          aggfunc=["mean", "count"])
    print(pivot["mean"].round(3).to_string())
    print("\n样本量:")
    print(pivot["count"].to_string())

    # 核心对比: Discovery高+RPS低 vs Discovery低+RPS低
    dh_rl = d[(d["disc_q"] == "高") & (d["rps_q"] == "低")]["fwd6"]
    dl_rl = d[(d["disc_q"] == "低") & (d["rps_q"] == "低")]["fwd6"]
    dh_rh = d[(d["disc_q"] == "高") & (d["rps_q"] == "高")]["fwd6"]
    print("\n=== 核心对比 (H2 正交假设) ===")
    print(f"  Discovery高 + RPS低 : n={len(dh_rl):>4}  fwd6={dh_rl.mean():>7.1%}")
    print(f"  Discovery低 + RPS低 : n={len(dl_rl):>4}  fwd6={dl_rl.mean():>7.1%}")
    print(f"  → 增量 (正交性)      : {(dh_rl.mean() - dl_rl.mean()):>+7.1%}")
    print(f"  Discovery高 + RPS高 : n={len(dh_rh):>4}  fwd6={dh_rh.mean():>7.1%}")

    # ============ E3: 覆盖率 ============
    print("\n=== E3: 探针覆盖率 ===")
    for probe in ["order", "capex", "margin"]:
        cov = df[probe].notna().mean()
        print(f"  {probe:<8}: {cov:.1%}")


if __name__ == "__main__":
    main()
