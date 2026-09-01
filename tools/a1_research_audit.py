"""A1 Research Audit — 价格 PIT 后的研究池/因子/画像变化（A vs A1）。

回答:
  1. A → A1 Top100 重合率（未来函数是"排序偏差"还是"研究对象改变"）
  2. 因子分布变化（RPS/PE/S1/S2 覆盖）
  3. 画像变化（市值/行业）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np
from pit.market import MarketData

DAY = "20220104"

def load(base):
    t = pd.read_csv(f"baseline/{base}/trades.csv", dtype={"code": str, "date": str})
    t["code"] = t["code"].str.zfill(6)
    nav = pd.read_csv(f"baseline/{base}/nav.csv", index_col=0, header=0)
    nav.index = nav.index.astype(str)
    return t, nav

def top_buys(t):
    return set(t[(t["direction"]=="buy") & (t["date"]==DAY)]["code"])

A_t, A_nav = load("pre_pit_A")
A1_t, A1_nav = load("a1_price_only")
A = top_buys(A_t)
A1 = top_buys(A1_t)

keep = A & A1
gone = A - A1
new = A1 - A
print("=" * 60)
print("A1 Research Audit: A(污染) vs A1(价格PIT, 规则仍失效)")
print("=" * 60)
print(f"Top100 重合: {len(keep)}% ({len(keep)}/100) | 消失 {len(gone)} | 新进 {len(new)}")

# 行业画像
ind = pd.read_csv("data/cache/sw_stock_industry.csv", dtype={"code": str})
ind_map = dict(zip(ind["code"], ind["sw1"]))
def ind_top(codes, n=5):
    return pd.Series([ind_map.get(c, "?") for c in codes]).value_counts().head(n).to_dict()

print(f"\nA 行业 Top5: {ind_top(A)}")
print(f"A1 行业 Top5: {ind_top(A1)}")
print(f"保留 行业 Top5: {ind_top(keep)}")
print(f"消失 行业 Top5: {ind_top(gone)}")
print(f"新进 行业 Top5: {ind_top(new)}")

# 市值画像
tdx = pd.read_csv("data/cache/tdx_financials.csv", dtype={"code": str, "report_date_str": str})
tdx["code"] = tdx["code"].str.zfill(6)
shares = tdx.sort_values("report_date_str").groupby("code").tail(1).set_index("code")["total_shares"]
mkt = MarketData()
def mcap_profile(codes, label):
    mc = {}
    for c in codes:
        df = mkt.as_of(c, DAY)
        if len(df) > 0:
            px = float(df["close"].iloc[-1])
            sh = shares.get(c, np.nan)
            if sh and sh > 0:
                mc[c] = px * sh / 1e8
    s = pd.Series(mc)
    if len(s) == 0:
        print(f"{label}: 无数据")
        return
    print(f"{label}: 中位 {s.median():.0f}亿 | <50亿 {(s<50).mean():.0%} | >200亿 {(s>200).mean():.0%}")

print("\n=== 市值画像 ===")
mcap_profile(A, "A")
mcap_profile(A1, "A1")
mcap_profile(keep, "保留")
mcap_profile(gone, "消失")
mcap_profile(new, "新进")

# 收益对比
print("\n=== 收益对比 ===")
for year in ["2022", "2023", "2024", "2025"]:
    a = A_nav[A_nav.index.str.startswith(year)]
    a1 = A1_nav[A1_nav.index.str.startswith(year)]
    if len(a) and len(a1):
        print(f"  {year}: A={a['nav'].iloc[-1]/a['nav'].iloc[0]-1:>8.1%}  A1={a1['nav'].iloc[-1]/a1['nav'].iloc[0]-1:>8.1%}  Δ={a1['nav'].iloc[-1]/a1['nav'].iloc[0]-a['nav'].iloc[-1]/a['nav'].iloc[0]:>+8.1%}")

# 整体
A_ret = A_nav["nav"].iloc[-1]/A_nav["nav"].iloc[0]-1
A1_ret = A1_nav["nav"].iloc[-1]/A1_nav["nav"].iloc[0]-1
A_dd = (A_nav["nav"]/A_nav["nav"].cummax()-1).min()
A1_dd = (A1_nav["nav"]/A1_nav["nav"].cummax()-1).min()
print(f"\n累计: A={A_ret:>8.1%}  A1={A1_ret:>8.1%}  Δ={A1_ret-A_ret:>+8.1%}")
print(f"回撤: A={A_dd:>8.1%}  A1={A1_dd:>8.1%}")
