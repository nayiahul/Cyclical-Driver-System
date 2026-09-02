"""State Transition Audit — 状态迁移的研究价值。

问题: 从"分类"升级到"机会发现"——股票的状态迁移 (L0→L1) 是否是最佳研究窗口?

数据: discovery_audit_2022_2025.csv (12 采样日, 每只股票跨期可追踪)

设计:
  对连续采样日 t1, t2 (间隔约 4 个月):
    - 股票在 t1 的状态 s1, t2 的状态 s2
    - 迁移事件: s1→s2 (如 L0→L1)
    - 统计: 迁移事件发生后 (t2 起) 未来 1/3/6 月收益

关键比较:
  L0→L1 (变化被发现) : 是否最佳研究窗口?
  L1→L2 (市场开始确认)
  L1→L1 (持续 L1)
  L2→L3 (确认完成)
  L3→L4 (兑现)
  L0→L0 (无变化, 对照)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

CSV = "baseline/discovery_audit_2022_2025.csv"
if not os.path.exists(CSV):
    print(f"⚠️ {CSV} 不存在, 请先运行 tools/discovery_audit.py (12 采样日版本)")
    sys.exit(1)

df = pd.read_csv(CSV)
df["code"] = df["code"].astype(str).str.zfill(6)
df["disc_q"] = np.where(df["discovery"] >= 0.5, "high", "low")
df["state"] = "L0"
df.loc[(df["disc_q"]=="high") & (df["rps"]<40), "state"] = "L1"
df.loc[(df["disc_q"]=="high") & (df["rps"]>=40) & (df["rps"]<70), "state"] = "L2"
df.loc[(df["disc_q"]=="high") & (df["rps"]>=70), "state"] = "L3"

days = sorted(df["day"].unique())
print(f"采样日: {[str(d) for d in days]}")
print(f"样本: {len(df)} 行")

# 状态迁移: 相邻采样日配对
transitions = []
for i in range(len(days) - 1):
    t1, t2 = days[i], days[i + 1]
    d1 = df[df["day"] == t1].set_index("code")[["state", "rps"]]
    d2 = df[df["day"] == t2].set_index("code")[["state", "rps"]]
    common = d1.index.intersection(d2.index)
    if len(common) == 0:
        continue
    for c in common:
        transitions.append({
            "code": c,
            "from_state": d1.loc[c, "state"],
            "to_state": d2.loc[c, "state"],
            "fwd1": df[(df["day"]==t2) & (df["code"]==c)]["fwd1"].values[0] if len(df[(df["day"]==t2) & (df["code"]==c)]) else np.nan,
            "fwd3": df[(df["day"]==t2) & (df["code"]==c)]["fwd3"].values[0] if len(df[(df["day"]==t2) & (df["code"]==c)]) else np.nan,
            "fwd6": df[(df["day"]==t2) & (df["code"]==c)]["fwd6"].values[0] if len(df[(df["day"]==t2) & (df["code"]==c)]) else np.nan,
        })

tdf = pd.DataFrame(transitions)
tdf["transition"] = tdf["from_state"] + "→" + tdf["to_state"]
print(f"\n迁移事件数: {len(tdf)}")

print("\n=== 迁移类型 × 未来收益 (fwd6) ===")
print(f"{'迁移':<10}{'n':>6}{'fwd1':>9}{'fwd3':>9}{'fwd6':>9}{'胜率':>8}")
for tr in ["L0→L0", "L0→L1", "L1→L1", "L1→L2", "L2→L2", "L2→L3", "L3→L3", "L1→L0", "L3→L1", "L3→L0"]:
    g = tdf[tdf["transition"] == tr]
    if len(g) < 30:
        continue
    f6 = g["fwd6"].dropna()
    f1 = g["fwd1"].dropna(); f3 = g["fwd3"].dropna()
    print(f"{tr:<10}{len(g):>6}{f1.mean():>8.1%}{f3.mean():>8.1%}{f6.mean():>8.1%}{(f6>0).mean():>7.1%}")

# 核心: L0→L1 (变化被发现) vs L0→L0 (无变化) vs L1→L1 (持续)
print("\n=== 核心对比 ===")
for tr, label in [("L0→L1", "变化被发现 (进入研究窗口)"),
                  ("L0→L0", "持续无变化 (对照)"),
                  ("L1→L1", "持续 L1 (已关注)"),
                  ("L1→L2", "市场开始确认"),
                  ("L2→L3", "确认完成")]:
    g = tdf[tdf["transition"] == tr]["fwd6"].dropna()
    if len(g):
        print(f"  {tr:<8} {label:<20} n={len(g):>5}  fwd6={g.mean():>7.1%}  胜率={(g>0).mean():.1%}")

tdf.to_csv("baseline/state_transitions.csv", index=False)
print(f"\n已保存 baseline/state_transitions.csv ({len(tdf)} 行)")
