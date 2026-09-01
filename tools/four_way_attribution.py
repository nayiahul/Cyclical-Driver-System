"""四版本归因: A / A1 / B1 / B — 三因素拆分。

A  (污染)      = 旧系统 (未来价格 + 规则失效 + 财务前视)
A1 (价格PIT)   = 真实价格 + 规则失效 + 财务前视
B1 (价格+规则) = 真实价格 + 规则恢复 + 财务前视
B  (完整PIT)   = 真实价格 + 规则恢复 + 财务治理

拆分:
  A  → A1 = 价格泄漏贡献
  A1 → B1 = 风控规则恢复贡献 (Feature Activation)
  B1 → B  = 财务泄漏贡献
  A  → B  = 总 PIT 修复贡献
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np

BASES = ["pre_pit_A", "a1_price_only", "b1_price_pit", "b_full_pit"]
LABELS = {"pre_pit_A": "A(污染)", "a1_price_only": "A1(价格PIT)",
          "b1_price_pit": "B1(价格+规则)", "b_full_pit": "B(完整PIT)"}

def load(base):
    nav = pd.read_csv(f"baseline/{base}/nav.csv", index_col=0, header=0)
    nav.index = nav.index.astype(str)
    trades = pd.read_csv(f"baseline/{base}/trades.csv", dtype={"code": str, "date": str})
    trades["code"] = trades["code"].str.zfill(6)
    return nav, trades

data = {}
for b in BASES:
    if not os.path.exists(f"baseline/{b}/nav.csv"):
        print(f"⚠️ {b} 缺失, 跳过")
        continue
    nav, trades = load(b)
    data[b] = {"nav": nav, "trades": trades}

def metrics(b):
    nav = data[b]["nav"]
    t = data[b]["trades"]
    ret = nav["nav"].iloc[-1] / nav["nav"].iloc[0] - 1
    ann = (1 + ret) ** (252 / len(nav)) - 1
    dd = (nav["nav"] / nav["nav"].cummax() - 1).min()
    buys = t[t["direction"] == "buy"]
    return ret, ann, dd, len(buys), buys["code"].nunique()

print("=" * 78)
print("四版本归因矩阵（2022-2025）")
print("=" * 78)
print(f"{'版本':<16}{'累计':>10}{'年化':>9}{'回撤':>9}{'买入笔':>8}{'股票数':>8}")
for b in data:
    ret, ann, dd, nbuy, nstk = metrics(b)
    print(f"{LABELS[b]:<16}{ret:>9.1%}{ann:>9.1%}{dd:>9.1%}{nbuy:>8d}{nstk:>8d}")

print("\n" + "=" * 78)
print("三因素拆分（差值）")
print("=" * 78)
pairs = [
    ("pre_pit_A", "a1_price_only", "价格泄漏贡献 (A→A1)"),
    ("a1_price_only", "b1_price_pit", "规则恢复贡献 (A1→B1)"),
    ("b1_price_pit", "b_full_pit", "财务泄漏贡献 (B1→B)"),
    ("pre_pit_A", "b_full_pit", "总 PIT 修复 (A→B)"),
]
for a, b, label in pairs:
    if a not in data or b not in data:
        continue
    ra, aa, da, _, _ = metrics(a)
    rb, ab, db, _, _ = metrics(b)
    print(f"{label:<28} 累计 {rb-ra:>+8.1%}  年化 {ab-aa:>+8.1%}  回撤 {db-da:>+8.1%}")

# 按年收益
print("\n" + "=" * 78)
print("按年收益对照")
print("=" * 78)
years = ["2022", "2023", "2024", "2025"]
print(f"{'年份':<6}" + "".join(f"{LABELS[b]:>14}" for b in data))
for y in years:
    row = f"{y:<6}"
    for b in data:
        n = data[b]["nav"]
        seg = n[n.index.str.startswith(y)]
        if len(seg) > 0:
            r = seg["nav"].iloc[-1] / seg["nav"].iloc[0] - 1
            row += f"{r:>13.1%}"
        else:
            row += f"{'—':>14}"
    print(row)

# 研究池重合（首日 Top100）
print("\n" + "=" * 78)
print("首调仓日研究池重合率")
print("=" * 78)
def top_codes(b):
    t = data[b]["trades"]
    return set(t[(t["direction"]=="buy") & (t["date"]=="20220104")]["code"])
pools = {b: top_codes(b) for b in data}
for b1 in data:
    for b2 in data:
        if b1 >= b2:
            continue
        inter = len(pools[b1] & pools[b2])
        print(f"  {LABELS[b1]:<14} ∩ {LABELS[b2]:<14} = {inter:>3}/100 ({inter:.0%})")
