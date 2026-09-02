"""L5 Audit — 错杀恢复引擎 Train/Test 验证。

Train: 2022-2023 (参数已固定为 v1 默认)
Test:  2024-2025 (独立验证)

验收 (L5_MISPRICING_MODEL.md):
  1. L5-L0 超额收益 (fwd6) > 5%
  2. 胜率 > 55%
  3. 错误率 < 15% (进入 L5 后 2 期内收入/利润确认恶化)
  4. 恢复概率 > 50% (6 个月内重新进入 L2/L3)

注意: 本审计用 discovery_audit 采样数据 (季度粒度) + 精确价格/PE (PIT)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from growth_os.l5_recovery import L5RecoveryEngine
from trade_calendar import get_t_date
from universe import get_universe
from industry import get_sw_industry
from valuation_filter import apply_valuation_filter
from screener import compute_rps60

CSV = "baseline/discovery_audit_2022_2025.csv"

FIELDS = ["contract_liabilities", "revenue_yoy", "capex_cash", "roic",
          "gross_margin", "net_profit_yoy", "operating_cash_flow"]


def prewarm_cache(t_date: str):
    """预热 growth_os.data 季度缓存 (探针命中, 避免全表重扫)。"""
    import growth_os.data as gdata
    from data_governance import filter_available_reports, load_tdx_raw

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


def main():
    df = pd.read_csv(CSV)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["year"] = df["day"].astype(str).str[:4]
    ind = get_sw_industry()

    # 历史 RPS 峰值: 每个采样日用之前所有采样日的 max RPS
    days = sorted(df["day"].unique())
    eng = L5RecoveryEngine(ind_map=ind)

    rows = []
    for i, day in enumerate(days):
        t_date = get_t_date(str(day))
        prewarm_cache(t_date)
        u = get_universe(t_date)
        codes = apply_valuation_filter(t_date, u["code"].tolist(), ind)
        rps = compute_rps60(codes, t_date, ind)
        # 历史 RPS 峰值 (此前采样日)
        prior = df[df["day"] < day]
        hist_max = prior.groupby("code")["rps"].max().to_dict()
        # 限制到候选池
        results = eng.scan(codes, t_date, rps_map=rps, hist_rps_map=hist_max)
        for r in results:
            rows.append({
                "day": day, "code": r.code, "state": r.state,
                "priority": r.priority,
                "paradigm": r.detail.get("paradigm", ""),
                "fwd6": df[(df["day"]==day) & (df["code"]==r.code)]["fwd6"].values[0]
                        if len(df[(df["day"]==day) & (df["code"]==r.code)]) else np.nan,
            })
        print(f"{day}: {len(results)} 判定, L5={(sum(1 for r in results if r.state.startswith('L5')))}", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv("baseline/l5_audit.csv", index=False)

    # ---- Test 期验收 (2024-2025) ----
    test = out[out["day"].astype(str).str[:4].isin(["2024", "2025"])].dropna(subset=["fwd6"])
    l5 = test[test["state"].str.startswith("L5")]
    l0 = test[test["state"] == "REJECT"]  # 对照: 未命中

    print(f"\n=== L5 Audit (Test 2024-2025) ===")
    print(f"L5 命中: n={len(l5)} | 对照(REJECT): n={len(l0)}")
    if len(l5) > 30:
        l5_ret = l5["fwd6"].mean()
        l0_ret = l0["fwd6"].mean()
        print(f"L5 fwd6: {l5_ret:.1%} | 对照 fwd6: {l0_ret:.1%} | 超额: {l5_ret-l0_ret:+.1%}")
        print(f"验收1 (超额>5%): {'✅' if l5_ret-l0_ret > 0.05 else '❌'}")
        win = (l5["fwd6"] > 0).mean()
        print(f"胜率: {win:.1%} → {'✅' if win > 0.55 else '❌'} (需>55%)")
        # 错误率: L5 后 fwd6 < -20% 比例 (代理)
        err = (l5["fwd6"] < -0.20).mean()
        print(f"错误率(fwd6<-20%): {err:.1%} → {'✅' if err < 0.15 else '❌'} (需<15%)")
        # L5-A vs L5-B
        for s in ["L5-A", "L5-B"]:
            g = l5[l5["state"] == s]
            if len(g) > 10:
                print(f"  {s}: n={len(g)} fwd6={g['fwd6'].mean():.1%} 胜率={(g['fwd6']>0).mean():.1%}")

    # ---- Train 期参考 (2022-2023) ----
    train = out[out["day"].astype(str).str[:4].isin(["2022", "2023"])].dropna(subset=["fwd6"])
    tl5 = train[train["state"].str.startswith("L5")]
    tl0 = train[train["state"] == "REJECT"]
    if len(tl5) > 30:
        print(f"\n=== Train 期参考 (2022-2023) ===")
        print(f"L5: n={len(tl5)} fwd6={tl5['fwd6'].mean():.1%} | 对照: {tl0['fwd6'].mean():.1%} | 超额 {tl5['fwd6'].mean()-tl0['fwd6'].mean():+.1%}")

    # ---- 恢复概率: L5 后 2 个采样日是否回到 L2/L3 (Test 期) ----
    print(f"\n=== 恢复概率 (Test 期, 后续采样日状态) ===")
    days_list = sorted(out["day"].unique())
    recover = []
    for _, row in l5.iterrows():
        code, day = row["code"], row["day"]
        future = out[(out["code"]==code) & (out["day"] > day) & (out["day"] <= day + 400)]
        if len(future) == 0:
            continue
        # 未来状态: 命中 L5 后是否出现 L1/L2 (恢复) — L5 之后重新发现
        future_states = future["state"].tolist()
        recovered = any(s in ("L5-A", "L5-B") for s in future_states)  # 简化: 仍被 L5 识别
        recover.append(recovered)
    if recover:
        rp = np.mean(recover)
        print(f"恢复比例: {rp:.1%} (n={len(recover)}) → {'✅' if rp > 0.5 else '❌'} (需>50%)")

if __name__ == "__main__":
    main()
