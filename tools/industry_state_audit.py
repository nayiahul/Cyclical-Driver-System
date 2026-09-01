"""Industry Adaptive State Machine Audit — 分行业状态有效性验证。

问题: 不同行业是否偏好不同状态? (周期行业 L1 优先 vs 成长行业 L2/L3 优先)

对每个行业: L0/L1/L2/L3 × fwd6 收益 + 胜率 → 最佳状态
输出: 行业范式映射建议 (Industry Paradigm Map v1 数据基础)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

df = pd.read_csv("baseline/discovery_audit.csv")
df["code"] = df["code"].astype(str).str.zfill(6)
df["disc_q"] = np.where(df["discovery"] >= 0.5, "high", "low")
df["state"] = "L0"
df.loc[(df["disc_q"]=="high") & (df["rps"]<40), "state"] = "L1"
df.loc[(df["disc_q"]=="high") & (df["rps"]>=40) & (df["rps"]<70), "state"] = "L2"
df.loc[(df["disc_q"]=="high") & (df["rps"]>=70), "state"] = "L3"

ind = pd.read_csv("data/cache/sw_stock_industry.csv", dtype={"code": str})
ind_map = dict(zip(ind["code"], ind["sw1"]))
df["ind"] = df["code"].map(ind_map).fillna("未知")

# 行业范式先验分组 (基于 growth_os/industry_paradigms.py 思想)
PARADIGM = {
    # 周期制造: 预期差在早期 (L1)
    "有色金属": "cycle_manufacturing", "基础化工": "cycle_manufacturing",
    "机械设备": "cycle_manufacturing", "钢铁": "cycle_manufacturing",
    "煤炭": "cycle_manufacturing", "石油石化": "cycle_manufacturing",
    "建筑材料": "cycle_manufacturing", "电力设备": "cycle_manufacturing",
    # 科技成长: 确认更重要 (L2/L3)
    "电子": "tech_growth", "通信": "tech_growth", "计算机": "tech_growth",
    "传媒": "tech_growth", "国防军工": "tech_growth",
    # 消费: 品牌/盈利修复 (L2)
    "食品饮料": "consumer", "医药生物": "consumer", "家用电器": "consumer",
    "纺织服饰": "consumer", "商贸零售": "consumer", "农林牧渔": "consumer",
    "社会服务": "consumer",
    # 金融/公用: 低波动 (L0/L2)
    "银行": "defensive", "非银金融": "defensive", "公用事业": "defensive",
    "交通运输": "defensive", "房地产": "defensive",
}
df["paradigm"] = df["ind"].map(PARADIGM).fillna("other")

print("=== 各行业 × 状态 fwd6 收益矩阵 (n≥30 才显示) ===")
print(f"{'行业':<8}{'L0':>8}{'L1':>8}{'L2':>8}{'L3':>8}{'最佳':>6}{'范式':>18}")
results = []
for ind_ in sorted(df["ind"].unique()):
    sub = df[df["ind"] == ind_]
    row = {"ind": ind_, "paradigm": PARADIGM.get(ind_, "other")}
    best_state, best_ret = None, -999
    for s in ["L0", "L1", "L2", "L3"]:
        g = sub[(sub["state"] == s)]["fwd6"].dropna()
        if len(g) >= 30:
            row[s] = g.mean()
            if row[s] > best_ret:
                best_ret, best_state = row[s], s
        else:
            row[s] = np.nan
    row["best"] = best_state
    results.append(row)

res = pd.DataFrame(results).set_index("ind")
res["L0"] = res["L0"].map(lambda x: f"{x:+.1%}" if not np.isnan(x) else "—")
res["L1"] = res["L1"].map(lambda x: f"{x:+.1%}" if not np.isnan(x) else "—")
res["L2"] = res["L2"].map(lambda x: f"{x:+.1%}" if not np.isnan(x) else "—")
res["L3"] = res["L3"].map(lambda x: f"{x:+.1%}" if not np.isnan(x) else "—")
print(res.to_string())

# 范式汇总
print("\n=== 范式汇总 (L1-L0 增量) ===")
for p in ["cycle_manufacturing", "tech_growth", "consumer", "defensive"]:
    sub = df[df["paradigm"] == p]
    l1 = sub[sub["state"]=="L1"]["fwd6"].dropna()
    l0 = sub[sub["state"]=="L0"]["fwd6"].dropna()
    l2 = sub[sub["state"]=="L2"]["fwd6"].dropna()
    l3 = sub[sub["state"]=="L3"]["fwd6"].dropna()
    print(f"  {p:<20} L1-L0: {l1.mean()-l0.mean():>+7.1%} (n={len(l1)}) | "
          f"L2-L0: {l2.mean()-l0.mean():>+7.1%} | L3-L0: {l3.mean()-l0.mean():>+7.1%}")

# 最佳状态分布
print("\n=== 各范式最佳状态分布 ===")
for p in ["cycle_manufacturing", "tech_growth", "consumer", "defensive"]:
    sub = res[res["paradigm"] == p]
    print(f"  {p:<20}: {sub['best'].value_counts().to_dict()}")
