"""A → B1 Impact Matrix — 市场层修复影响评估。

比较 PRE-PIT A vs B1（价格 PIT + 乖离/流动性恢复）:
- 收益/回撤/交易
- 研究池画像（行业/市值/估值）
- Top50 重合率 + 新进/退出
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np

def load(base):
    nav = pd.read_csv(f"baseline/{base}/nav.csv", index_col=0, header=0)
    trades = pd.read_csv(f"baseline/{base}/trades.csv", dtype={"code": str, "date": str})
    trades["code"] = trades["code"].str.zfill(6)
    return nav, trades

def stats(base):
    nav, trades = load(base)
    ret = nav["nav"].iloc[-1] / nav["nav"].iloc[0] - 1
    peak = nav["nav"].cummax()
    dd = (nav["nav"] / peak - 1).min()
    buys = trades[trades["direction"] == "buy"]
    codes = buys["code"].nunique()
    return {
        "nav": nav, "trades": trades,
        "total_return": ret, "max_dd": dd,
        "n_buy_trades": len(buys), "n_stocks": codes,
    }

def industry_share(trades):
    ind = pd.read_csv("data/cache/sw_stock_industry.csv", dtype={"code": str})
    ind_map = dict(zip(ind["code"], ind["sw1"]))
    t = trades[trades["direction"] == "buy"].copy()
    t["ind"] = t["code"].map(ind_map).fillna("未知")
    t["amt"] = t["qty"] * t["price"]
    return t.groupby("ind")["amt"].sum().sort_values(ascending=False)

def top50_codes(trades, day="20220104"):
    """首个调仓日的买入代码（近似 Top50 研究池）。"""
    buys = trades[(trades["direction"] == "buy") & (trades["date"] == day)]
    return set(buys["code"])

A = stats("pre_pit_A")
B1 = stats("b1_price_pit")

print("=" * 60)
print("A → B1 Impact Matrix（2022-2025）")
print("=" * 60)
print(f"{'指标':<22}{'A (污染)':>14}{'B1 (价格PIT)':>14}{'变化':>10}")
print(f"{'累计收益':<22}{A['total_return']:>13.1%}{B1['total_return']:>14.1%}{B1['total_return']-A['total_return']:>+9.1%}")
print(f"{'最大回撤':<22}{A['max_dd']:>13.1%}{B1['max_dd']:>14.1%}{B1['max_dd']-A['max_dd']:>+9.1%}")
print(f"{'买入交易笔数':<22}{A['n_buy_trades']:>14d}{B1['n_buy_trades']:>14d}{B1['n_buy_trades']-A['n_buy_trades']:>+9d}")
print(f"{'股票数量':<22}{A['n_stocks']:>14d}{B1['n_stocks']:>14d}{B1['n_stocks']-A['n_stocks']:>+9d}")

# 研究池对比（首调仓日 Top 买入）
a_top = top50_codes(A["trades"])
b_top = top50_codes(B1["trades"])
inter = a_top & b_top
print(f"\n首调仓日研究池: A={len(a_top)} B1={len(b_top)} 重合={len(inter)} ({len(inter)/max(len(a_top),1):.0%})")
print(f"  新进入(B1独有): {sorted(b_top - a_top)[:8]}...")
print(f"  退出(A独有): {sorted(a_top - b_top)[:8]}...")

# 行业分布变化
a_ind = industry_share(A["trades"])
b_ind = industry_share(B1["trades"])
merged = pd.DataFrame({"A": a_ind, "B1": b_ind}).fillna(0)
merged["diff"] = merged["B1"] - merged["A"]
print(f"\n行业分布变化 (B1 - A, 亿元):")
for ind_, r in merged.reindex(merged["diff"].abs().sort_values(ascending=False).index).head(8).iterrows():
    print(f"  {ind_:<8} A={r['A']/1e8:>7.1f}亿 B1={r['B1']/1e8:>7.1f}亿 Δ={r['diff']/1e8:>+7.1f}亿")

# 按年收益
print("\n按年收益对比:")
for year in ["2022", "2023", "2024", "2025"]:
    a_nav = A["nav"][A["nav"].index.str.startswith(year)]
    b_nav = B1["nav"][B1["nav"].index.str.startswith(year)]
    if len(a_nav) > 0 and len(b_nav) > 0:
        a_r = a_nav.iloc[-1] / a_nav.iloc[0] - 1
        b_r = b_nav.iloc[-1] / b_nav.iloc[0] - 1
        print(f"  {year}: A={a_r:>8.1%}  B1={b_r:>8.1%}  Δ={b_r-a_r:>+8.1%}")
