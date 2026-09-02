"""Step 6-A.0: Research Compression Audit — 压缩规则有效性验证

问题: 498 → 50 的压缩规则 (RPI v1 雏形) 是否真的提高研究质量?

设计:
  对每个采样日, 按 RPI 排序取 Top 50, 对比全池:
    - fwd6 均值 / 胜率
    - Winner Capture (Top10% 命中率)
    - False Positive (fwd6 < -20% 比例)
    - 恢复率 (L5 子集)

RPI v1 雏形 (全部用当前可得信息, 无未来数据):
  0.4 lifecycle + 0.3 evidence + 0.2 mispricing + 0.1 executability

  注意: 本审计为"规则验证", 不是新选股模型 — 回答研究资源分配是否有效
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

aud = pd.read_csv("baseline/discovery_audit_2022_2025.csv")
aud["code"] = aud["code"].astype(str).str.zfill(6)
aud["day"] = aud["day"].astype(int)

# L5 标记 (l5_recovery_v2)
l5r = pd.read_csv("baseline/l5_recovery_v2.csv")
l5r["code"] = l5r["code"].astype(str).str.zfill(6)
l5r["day"] = l5r["day"].astype(int)
l5_map = {(r["code"], r["day"]): r["state"] for _, r in l5r.iterrows()}

# 状态重建
aud["disc_q"] = np.where(aud["discovery"] >= 0.5, "high", "low")
def st(rps, disc):
    if disc >= 0.5:
        if rps >= 70: return "L3"
        if rps >= 40: return "L2"
        return "L1"
    return "L0"
aud["state"] = [st(r, d) for r, d in zip(aud["rps"], aud["discovery"])]
aud["state"] = [l5_map.get((c, d), s) for c, d, s in zip(aud["code"], aud["day"], aud["state"])]

# --- RPI v1 雏形 ---
# 1. lifecycle (40%): L5-A > L5-B > L1 > L2 > L3 > L0
lc = {"L5-A": 1.0, "L5-B": 0.8, "L1": 0.7, "L2": 0.5, "L3": 0.3, "L0": 0.1}
aud["lc_score"] = aud["state"].map(lc).fillna(0.1)

# 2. evidence (30%): 探针 green 密度
aud["ev_score"] = (aud["order"] + aud["capex"] + aud["margin"]) / 3.0
aud["ev_score"] = aud["ev_score"].fillna(0.0)

# 3. mispricing (20%): Discovery高 + RPS低 的错配程度
aud["ms_score"] = aud["discovery"].fillna(0) * (1 - aud["rps"] / 100.0).clip(0, 1)
aud["ms_score"] = aud["ms_score"].fillna(0.0)

# 4. executability (10%): 数据完整度 (探针非 NaN 比例)
aud["ex_score"] = aud[["order", "capex", "margin"]].notna().mean(axis=1)

aud["rpi"] = (0.4 * aud["lc_score"] + 0.3 * aud["ev_score"]
              + 0.2 * aud["ms_score"] + 0.1 * aud["ex_score"])

# --- 压缩模拟: 每采样日 Top 50 ---
def pool_stats(df, label):
    f6 = df["fwd6"].dropna()
    if len(f6) == 0:
        print(f"  {label}: 无数据")
        return
    cutoff = aud["fwd6"].quantile(0.9)
    print(f"  {label:<12} n={len(df):>4}  fwd6={f6.mean():>7.1%}  胜率={(f6>0).mean():>5.0%}"
          f"  Top10%命中={(f6>cutoff).mean():>5.1%}  失败率={(f6<-0.2).mean():>5.1%}")

print("=== Research Compression Audit (2022-2025 全样本) ===")
pool_stats(aud, "全池(基线)")

# Top 50 / Top 100 / Top 200 对比
for n in [200, 100, 50, 30]:
    top = aud.sort_values(["day", "rpi"], ascending=[True, False]).groupby("day").head(n)
    pool_stats(top, f"Top{n}")

# 分年
print("\n=== 分年 Top50 vs 全池 ===")
for y in ["2022", "2023", "2024", "2025"]:
    sub = aud[aud["day"].astype(str).str[:4] == y]
    top = sub.sort_values("rpi", ascending=False).groupby("day").head(50)
    f6_all = sub["fwd6"].dropna()
    f6_top = top["fwd6"].dropna()
    if len(f6_top) > 0:
        print(f"  {y}: 全池 {f6_all.mean():>7.1%} → Top50 {f6_top.mean():>7.1%}"
              f" (Δ {f6_top.mean()-f6_all.mean():+.1%})  n={len(f6_top)}")

# L5 子集恢复率 (压缩是否保留高恢复样本)
print("\n=== L5 恢复率: 全 L5 vs Top50 内 L5 ===")
l5_all = aud[aud["state"].str.startswith("L5")]
l5_top50 = aud.sort_values(["day", "rpi"], ascending=[True, False]).groupby("day").head(50)
l5_top50 = l5_top50[l5_top50["state"].str.startswith("L5")]
print(f"  全 L5: n={len(l5_all)} | Top50 内 L5: n={len(l5_top50)}")
print(f"  (恢复率用 l5_recovery_v2 的 R2: 基线 50.2%)")

# RPI 分层单调性
print("\n=== RPI 分层 fwd6 (全样本) ===")
aud["rpi_q"] = pd.qcut(aud["rpi"], 5, labels=["Q1低", "Q2", "Q3", "Q4", "Q5高"])
for q in ["Q1低", "Q2", "Q3", "Q4", "Q5高"]:
    g = aud[aud["rpi_q"] == q]["fwd6"].dropna()
    print(f"  {q}: n={len(g):>5}  fwd6={g.mean():>7.1%}")

aud.to_csv("baseline/compression_audit.csv", index=False)
print("\n已保存 baseline/compression_audit.csv")
