"""Winner Capture Audit — 研究池质量 (赔率视角)。

L1 池 vs 全市场:
  Top10% 捕获率 (Capture Ratio)
  翻倍概率 (+50% / +100%)
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

f6 = df.dropna(subset=["fwd6"]).copy()
l1 = f6[f6["state"] == "L1"]

print(f"=== Winner Capture Audit (fwd6) ===")
print(f"全市场: n={len(f6)} | L1池: n={len(l1)}")

for thr_label, pct in [("Top10%", 0.90), ("Top20%", 0.80)]:
    cutoff = f6["fwd6"].quantile(pct)
    mkt_rate = (f6["fwd6"] > cutoff).mean()
    l1_rate = (l1["fwd6"] > cutoff).mean()
    print(f"\n{thr_label} (涨幅>{cutoff:.0%}):")
    print(f"  全市场占比: {mkt_rate:.1%} | L1占比: {l1_rate:.1%} | Capture Ratio: {l1_rate/mkt_rate:.2f}")

print("\n大赢家概率:")
for label, thr in [("+50%", 0.5), ("+100%", 1.0)]:
    mkt = (f6["fwd6"] > thr).mean()
    l = (l1["fwd6"] > thr).mean()
    print(f"  fwd6>{label}: 全市场 {mkt:.1%} | L1 {l:.1%} | 比值 {l/mkt:.2f}")

# 按范式拆分
ind = pd.read_csv("data/cache/sw_stock_industry.csv", dtype={"code": str})
ind_map = dict(zip(ind["code"], ind["sw1"]))
f6["ind"] = f6["code"].map(ind_map).fillna("未知")
print("\nL1 Top10% 捕获率按范式:")
for p, inds in [("周期制造", ["有色金属","基础化工","机械设备","钢铁","煤炭","石油石化","建筑材料"]),
                ("科技成长", ["电子","通信","计算机","传媒","国防军工"]),
                ("消费", ["食品饮料","医药生物","家用电器","纺织服饰","农林牧渔"])]:
    sub = f6[f6["ind"].isin(inds)]
    l1sub = l1[l1["ind"].isin(inds)]
    if len(l1sub) < 30:
        continue
    cutoff = sub["fwd6"].quantile(0.9)
    mkt = (sub["fwd6"] > cutoff).mean()
    l = (l1sub["fwd6"] > cutoff).mean()
    print(f"  {p:<8}: L1 {l:.1%} vs 市场 {mkt:.1%} | Ratio {l/mkt:.2f}")
