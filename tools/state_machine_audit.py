"""State Machine Audit v1 — L0-L5 状态机研究价值验证。

数据: baseline/discovery_audit.csv (12,268 行, 6 季度采样, B 状态 PIT)
验证矩阵:
  1. 状态收益分布 (L0-L3 × fwd1/3/6)
  2. 胜率
  3. 回撤风险 (最大亏损 / 亏损>20% 比例)
  4. 行业拆分 (周期 vs 非周期)
  5. Composite Top vs L1 State Pool 对比

通过标准 (L1):
  C1: fwd6 L1 > L0
  C2: fwd6 L1 > L3
  C3: n(L1) > 500
  C4: L1 - L3 > 3pp
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

df = pd.read_csv("baseline/discovery_audit.csv")
print(f"总样本: {len(df)} 行 | 日期: {sorted(df['day'].unique())}")

# ---- 状态分类 (与 state_machine 一致: 阈值 RPS 40/70, Discovery 0.5) ----
df["disc_q"] = np.where(df["discovery"] >= 0.5, "high", "low")
df["state"] = "L0"
df.loc[(df["disc_q"] == "high") & (df["rps"] < 40), "state"] = "L1"
df.loc[(df["disc_q"] == "high") & (df["rps"] >= 40) & (df["rps"] < 70), "state"] = "L2"
df.loc[(df["disc_q"] == "high") & (df["rps"] >= 70), "state"] = "L3"

print("\n=== 1. 状态收益分布 ===")
print(f"{'状态':<4}{'n':>6}{'fwd1':>9}{'fwd3':>9}{'fwd6':>9}{'fwd6胜率':>9}")
for s in ["L0", "L1", "L2", "L3"]:
    g = df[df["state"] == s]
    if len(g) == 0:
        continue
    f1 = g["fwd1"].dropna(); f3 = g["fwd3"].dropna(); f6 = g["fwd6"].dropna()
    print(f"{s:<4}{len(g):>6}{f1.mean():>8.1%}{f3.mean():>8.1%}{f6.mean():>8.1%}{(f6>0).mean():>8.1%}")

# ---- 2. 胜率 ----
print("\n=== 2. 胜率 (fwd6>0) ===")
for s in ["L0", "L1", "L2", "L3"]:
    g = df[df["state"] == s]["fwd6"].dropna()
    if len(g): print(f"  {s}: {(g>0).mean():.1%} (n={len(g)})")

# ---- 3. 回撤风险 ----
print("\n=== 3. 回撤风险 (fwd6) ===")
for s in ["L0", "L1", "L2", "L3"]:
    g = df[df["state"] == s]["fwd6"].dropna()
    if len(g):
        print(f"  {s}: 最大亏损 {g.min():.1%} | 亏损>20% 比例 {(g < -0.2).mean():.1%}")

# ---- 4. 行业拆分 ----
ind = pd.read_csv("data/cache/sw_stock_industry.csv", dtype={"code": str})
ind_map = dict(zip(ind["code"], ind["sw1"]))
df["ind"] = df["code"].map(ind_map).fillna("未知")
print("\n=== 4. 行业拆分 (L1 vs L0, fwd6) ===")
print(f"{'行业':<10}{'L1 n':>6}{'L1 fwd6':>9}{'L0 n':>6}{'L0 fwd6':>9}{'增量':>8}")
for ind_ in ["电子", "通信", "有色金属", "机械设备", "电力设备", "基础化工", "汽车", "医药生物"]:
    l1 = df[(df["state"] == "L1") & (df["ind"] == ind_)]["fwd6"].dropna()
    l0 = df[(df["state"] == "L0") & (df["ind"] == ind_)]["fwd6"].dropna()
    if len(l1) >= 30 and len(l0) >= 30:
        print(f"{ind_:<10}{len(l1):>6}{l1.mean():>8.1%}{len(l0):>6}{l0.mean():>8.1%}{l1.mean()-l0.mean():>+7.1%}")

# ---- 5. Composite Top vs L1 Pool ----
print("\n=== 5. Composite Top vs L1 State Pool (fwd6) ===")
# 代理: Composite 排名≈RPS 排名 (确认链) → 用 RPS Top 30% 作为 Composite 代理
top_rps = df[df["rps"] >= df["rps"].quantile(0.7)]["fwd6"].dropna()
l1_pool = df[df["state"] == "L1"]["fwd6"].dropna()
l1r_pool = df[(df["state"] == "L1") & (df["rps"] >= df["rps"].quantile(0.7))]["fwd6"].dropna()
print(f"  RPS Top30% (Confirmation代理): n={len(top_rps):>5}  fwd6={top_rps.mean():>7.1%}  胜率={(top_rps>0).mean():.1%}")
print(f"  L1 Pool (Discovery高+RPS低)   : n={len(l1_pool):>5}  fwd6={l1_pool.mean():>7.1%}  胜率={(l1_pool>0).mean():.1%}")
print(f"  L1 ∩ RPS Top30% (重叠)        : n={len(l1r_pool):>5}  fwd6={l1r_pool.mean():>7.1%}")

# ---- 通过标准 ----
l1 = df[df["state"] == "L1"]["fwd6"].dropna()
l0 = df[df["state"] == "L0"]["fwd6"].dropna()
l3 = df[df["state"] == "L3"]["fwd6"].dropna()
print("\n=== 通过标准 ===")
print(f"  C1 (L1>{'L0'}: {l1.mean():.1%} > {l0.mean():.1%}): {'✅' if l1.mean() > l0.mean() else '❌'}")
print(f"  C2 (L1>L3): {l1.mean():.1%} > {l3.mean():.1%}): {'✅' if l1.mean() > l3.mean() else '❌'}")
print(f"  C3 (n(L1)>500): n={len(l1)}: {'✅' if len(l1) > 500 else '❌'}")
print(f"  C4 (L1-L3>3pp): {l1.mean()-l3.mean():.1%}: {'✅' if l1.mean()-l3.mean() > 0.03 else '❌'}")
