"""Research Allocation v1 — 雷达配额研究分配 (替代全局 RPI 排序)。

架构修正 (来自 Compression Audit 负结果):
  全局单分排序 → Recovery 坍缩, L1 被挤出 (Top50 内 L1=0)
  修正: 双雷达独立排序 + 配额分配 (Growth 25 + Recovery 25)

Growth RA (L1/L2 内部): 变化强度30% + 未确认30% + 生命周期20% + 可执行20%
Recovery RA (L5 内部): 错杀质量30% + 基本面完整30% + 恢复潜力20% + 风险20%

最低质量门槛 (宁缺勿滥):
  Growth: ≥1 个 green 探针
  Recovery: L5 Layer3 通过 (L5-A/B 已含)

验证指标 (非收益):
  Growth Top25: L1→L2/L3 升级率 ≥ 46.4% 基线
  Recovery Top25: L5 恢复率 ≥ 50.2% 基线
  双雷达完整性: 两雷达均保留
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

aud = pd.read_csv("baseline/compression_audit.csv")
aud["code"] = aud["code"].astype(str).str.zfill(6)
aud["day"] = aud["day"].astype(int)
days = sorted(aud["day"].unique())

# --- 双雷达 RA 分数 ---
aud["n_green"] = (aud[["order", "capex", "margin"]] >= 0.5).sum(axis=1)
aud["n_red"] = (aud[["order", "capex", "margin"]] == 0).sum(axis=1)
aud["ev"] = aud["ev_score"]
aud["unconfirmed"] = (1 - aud["rps"] / 100.0).clip(0, 1)
aud["exec"] = aud["ex_score"]

# Growth RA (L1/L2): 变化强度 + 未确认 + 生命周期(升级概率) + 可执行
aud["growth_ra"] = (0.3 * aud["ev"] + 0.3 * aud["unconfirmed"]
                    + 0.2 * np.where(aud["state"] == "L1", 1.0,
                                     np.where(aud["state"] == "L2", 0.6, 0.0))
                    + 0.2 * aud["exec"])

# Recovery RA (L5): 错杀质量(L5-A>B) + 基本面完整(非red) + 恢复潜力(RPS低位) + 风险(非red)
aud["recovery_ra"] = (0.3 * np.where(aud["state"] == "L5-A", 1.0,
                                     np.where(aud["state"] == "L5-B", 0.75, 0.0))
                      + 0.3 * (1 - aud["n_red"] / 3.0)
                      + 0.2 * aud["unconfirmed"]
                      + 0.2 * (1 - aud["n_red"] / 3.0))

# --- 配额分配 (每采样日) ---
growth_pool = aud[(aud["state"].isin(["L1", "L2"])) & (aud["n_green"] >= 1)]
recovery_pool = aud[aud["state"].str.startswith("L5")]

sel_growth = growth_pool.sort_values(["day", "growth_ra"], ascending=[True, False]).groupby("day").head(25)
sel_recovery = recovery_pool.sort_values(["day", "recovery_ra"], ascending=[True, False]).groupby("day").head(25)
top50 = pd.concat([sel_growth, sel_recovery])

print(f"=== Research Allocation v1 (Radar-Quota) ===")
print(f"Growth 池: {len(growth_pool)} → Top25/日: {len(sel_growth)}")
print(f"Recovery 池: {len(recovery_pool)} → Top25/日: {len(sel_recovery)}")
print(f"双雷达完整性: Growth {len(sel_growth)} 只 + Recovery {len(sel_recovery)} 只 ✅")

# --- 验证 1: Growth Top25 升级率 ---
trans = []
for i in range(len(days) - 1):
    d1, d2 = days[i], days[i + 1]
    top_codes = set(sel_growth[sel_growth["day"] == d1]["code"])
    s1 = aud[aud["day"] == d1].set_index("code")
    s2 = aud[aud["day"] == d2].set_index("code")
    for c in top_codes.intersection(s2.index):
        if s1.loc[c, "state"] == "L1":
            trans.append(s2.loc[c, "state"] in ("L2", "L3"))
if trans:
    up = np.mean(trans)
    print(f"\nGrowth Top25 内 L1 升级率: {up:.1%} (基线 46.4%) → {'✅' if up >= 0.464 else '❌'} (n={len(trans)})")

# --- 验证 2: Recovery Top25 恢复 (fwd6 失败率 + rps 回升) ---
rec_top = sel_recovery
f6 = rec_top["fwd6"].dropna()
print(f"\nRecovery Top25: n={len(f6)} fwd6={f6.mean():.1%} 失败率={(f6 < -0.2).mean():.1%} (基线 12.7%)")
print(f"  (恢复率验证需 l5_recovery_v2 合并, 见下)")

# 用 l5_recovery_v2 精确验证恢复率
l5r = pd.read_csv("baseline/l5_recovery_v2.csv")
l5r["code"] = l5r["code"].astype(str).str.zfill(6)
l5r["day"] = l5r["day"].astype(int)
merged = sel_recovery.merge(l5r[["code", "day", "R2_state"]], on=["code", "day"], how="left")
if len(merged) > 0:
    r2 = merged["R2_state"].dropna()
    if len(r2) > 0:
        print(f"Recovery Top25 恢复率 (R2): {r2.mean():.1%} (基线 50.2%) → {'✅' if r2.mean() >= 0.502 else '❌'} (n={len(r2)})")

# --- 验证 3: red 密度 ---
print(f"\n基本面 red 密度: Top50 {top50['n_red'].mean():.2f} vs 全池 {aud['n_red'].mean():.2f}")

# --- 输出研究队列 ---
top50.to_csv("baseline/research_allocation_v1.csv", index=False)
print(f"\n已保存 baseline/research_allocation_v1.csv ({len(top50)} 行)")
print("\n=== 每雷达 Top5 样例 (最近采样日) ===")
last_day = days[-1]
for radar, sel in [("Growth", sel_growth), ("Recovery", sel_recovery)]:
    sub = sel[sel["day"] == last_day].head(5)
    print(f"\n[{radar}] {last_day}")
    for _, r in sub.iterrows():
        print(f"  {r['code']} state={r['state']} RA={r['growth_ra'] if radar=='Growth' else r['recovery_ra']:.2f} "
              f"green={r['n_green']} red={r['n_red']} rps={r['rps']:.0f}")
