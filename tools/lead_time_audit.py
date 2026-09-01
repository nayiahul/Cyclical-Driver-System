"""Lead Time Audit — 领先性验证 (季度级近似)。

Event A (T0): 首次进入 L1 (Discovery 高 + RPS 低) → 经营变化已发生、市场未确认
Event B (T1): 首次进入 L2/L3 (RPS 确认) → 市场开始确认
Lead Time = T1 - T0 (采样周期数)

验收: 中位领先 >= 1 采样周期, 领先>0 比例 >= 60%
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

CSV = "baseline/discovery_audit_2022_2025.csv"
df = pd.read_csv(CSV)
df["code"] = df["code"].astype(str).str.zfill(6)
df["disc_q"] = np.where(df["discovery"] >= 0.5, "high", "low")
df["state"] = "L0"
df.loc[(df["disc_q"]=="high") & (df["rps"]<40), "state"] = "L1"
df.loc[(df["disc_q"]=="high") & (df["rps"]>=40) & (df["rps"]<70), "state"] = "L2"
df.loc[(df["disc_q"]=="high") & (df["rps"]>=70), "state"] = "L3"

days = sorted(df["day"].unique())
day_idx = {d: i for i, d in enumerate(days)}

leads = []
for code, g in df.groupby("code"):
    g = g.sort_values("day")
    t0 = None
    for _, row in g.iterrows():
        if row["state"] == "L1" and t0 is None:
            t0 = day_idx[row["day"]]
        if row["state"] in ("L2", "L3") and t0 is not None:
            leads.append(day_idx[row["day"]] - t0)
            break

leads = np.array(leads)
print(f"=== Lead Time Audit (n={len(leads)}) ===")
print(f"采样周期数: {len(days)}, 间隔约 {365/len(days)*4:.0f} 天/周期" if len(days) else "")
print(f"领先分布: 中位={np.median(leads):.0f} 周期 | 均值={leads.mean():.1f} | 25%={np.percentile(leads,25):.0f} | 75%={np.percentile(leads,75):.0f}")
print(f"领先>0 比例: {(leads>0).mean():.0%}")
print(f"领先>=1 周期比例: {(leads>=1).mean():.0%}")
ok = np.median(leads) >= 1 and (leads > 0).mean() >= 0.6
print(f"验收(中位>=1且领先>0比例>=60%): {'✅ PASS' if ok else '❌ FAIL'}")
