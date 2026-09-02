"""Step 9-C1: Expectation State Audit — H-E1 验证。

问题: L1 中加 E0/E1（低认知区）是否提高 L2/L3 升级率?

分组:
  A: L1 全部 (基线, 升级率 46.4%)
  B: L1 + E0 (变化 + 市场忽略)
  C: L1 + E1 (变化 + 少数关注)
  D: L1 + E2+ (市场已关注)

E 状态 v0 (代理, 无分析师数据):
  E0: RPS < 30 且 盈利冲击正向/中性 (市场忽略)
  E1: RPS 30-60 (少数关注)
  E2: RPS >= 60 (市场确认)

Earnings Surprise Proxy (方向确认):
  Positive: 单季 yoy 加速 (用 discovery 字段近似)
  用已有 discovery/capex/margin 探针状态替代 (v0)

关键: 反向实验 — E0 停留率 (若 E0 长期不升级 = 市场不认可, 非预期差)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

aud = pd.read_csv("baseline/discovery_audit_2022_2025.csv")
aud["code"] = aud["code"].astype(str).str.zfill(6)
aud["day"] = aud["day"].astype(int)

# 状态重建 (同 state_machine)
aud["disc_q"] = np.where(aud["discovery"] >= 0.5, "high", "low")
def st(rps, disc):
    if disc == "high":
        if rps >= 70: return "L3"
        if rps >= 40: return "L2"
        return "L1"
    return "L0"
aud["state"] = [st(r, d) for r, d in zip(aud["rps"], aud["disc_q"])]

# Earnings Surprise Proxy: discovery 探针强度 (正向冲击代理)
aud["shock"] = np.where((aud["order"] >= 0.5) & (aud["margin"] >= 0.5), "positive",
               np.where((aud["order"] < 0.5) & (aud["margin"] < 0.5), "negative", "neutral"))

# E 状态: 基于 RPS (价格关注代理) + shock
def e_state(rps, shock):
    if rps < 30:
        return "E0" if shock != "negative" else "E0x"  # E0x: 忽略且有负面冲击
    if rps < 60:
        return "E1"
    return "E2"
aud["E"] = [e_state(r, s) for r, s in zip(aud["rps"], aud["shock"])]

# L1 子集
l1 = aud[aud["state"] == "L1"]
print(f"L1 总数: {len(l1)}")
print(f"\nE 状态分布 (L1 内):")
print(l1["E"].value_counts().to_string())

# 状态迁移 (升级率)
days = sorted(aud["day"].unique())
rows = []
for i in range(len(days) - 1):
    d1, d2 = days[i], days[i + 1]
    s1 = aud[aud["day"] == d1].set_index("code")
    s2 = aud[aud["day"] == d2].set_index("code")
    common = s1.index.intersection(s2.index)
    for c in common:
        if s1.loc[c, "state"] == "L1":
            rows.append({
                "code": c, "day": d1, "E": s1.loc[c, "E"],
                "upgraded": s2.loc[c, "state"] in ("L2", "L3"),
                "stayed_l1": s2.loc[c, "state"] == "L1",
                "fell": s2.loc[c, "state"] == "L0",
            })
t = pd.DataFrame(rows)
print(f"\nL1 迁移事件: {len(t)}")

print("\n=== H-E1: 各 E 组升级率 ===")
print(f"{'组':<8}{'n':>6}{'升级L2/L3':>10}{'停留L1':>9}{'回落L0':>9}")
for g, label in [("A_all", "A 全部L1"), ("E0", "B L1+E0"), ("E0x", "B' L1+E0x"),
                 ("E1", "C L1+E1"), ("E2", "D L1+E2")]:
    if g == "A_all":
        sub = t
    else:
        sub = t[t["E"] == g]
    if len(sub) == 0:
        continue
    print(f"{label:<10}{len(sub):>6}{sub['upgraded'].mean():>9.1%}"
          f"{sub['stayed_l1'].mean():>8.1%}{sub['fell'].mean():>8.1%}")

# 基线对比
base = t["upgraded"].mean()
e0 = t[t["E"] == "E0"]["upgraded"].mean() if len(t[t["E"] == "E0"]) else np.nan
e0x = t[t["E"] == "E0x"]["upgraded"].mean() if len(t[t["E"] == "E0x"]) else np.nan
e1 = t[t["E"] == "E1"]["upgraded"].mean() if len(t[t["E"] == "E1"]) else np.nan
print(f"\n基线升级率: {base:.1%}")
print(f"H-E1: L1+E0 ({e0:.1%}) vs 基线 ({base:.1%}) → {'✅' if e0 > base else '❌'}")
print(f"H-E1b: L1+E0x ({e0x:.1%}) vs 基线 → {'⚠️ 高(市场忽略有原因?)' if e0x > base else '✅ 低(负面冲击有效过滤)'}")

# fwd6 对照
l1_fwd = aud[(aud["state"] == "L1")].dropna(subset=["fwd6"])
print("\n=== fwd6 对照 (L1 子集) ===")
for e in ["E0", "E0x", "E1", "E2"]:
    sub = l1_fwd[l1_fwd["E"] == e]
    if len(sub):
        print(f"  {e}: n={len(sub):>5} fwd6={sub['fwd6'].mean():>7.1%} 失败率={(sub['fwd6']<-0.2).mean():>5.1%}")

# 保存
aud.to_csv("baseline/expectation_audit.csv", index=False)
t.to_csv("baseline/expectation_transitions.csv", index=False)
print(f"\n已保存 expectation_audit.csv + expectation_transitions.csv")
