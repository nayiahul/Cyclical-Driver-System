"""Feature Activation Impact — 乖离率/流动性规则恢复后被剔除股票的画像。

回答: 新恢复的两条规则删掉的是"垃圾小票"还是"早期成长股"？
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np

from trade_calendar import get_t_date
from universe import get_universe
from industry import get_sw_industry
from pit.market import MarketData

t_date = get_t_date("20220104")
u = get_universe(t_date)
ind = get_sw_industry()
codes = u["code"].tolist()

# 复算 valuation filter 并捕获移除明细
import valuation_filter as vf
original = vf.apply_valuation_filter

removed_by_rule = {"deviation": [], "liquidity": []}
# 直接内联复算（避免改动原函数）：加载数据，逐规则判断
from data_governance import filter_available_reports_dash, load_tdx_raw, filter_available_reports
from config.params import PEG_MAX, STOCKS_DIR

fin = pd.read_csv("data/cache/financial_data.csv", dtype={"code": str})
fin = filter_available_reports_dash(fin, "date", t_date)
fin["date"] = pd.to_datetime(fin["date"])
fin_by_code = {c: g for c, g in fin.groupby("code")}
tdx = load_tdx_raw()
tdx = filter_available_reports(tdx, t_date)
tdx_by_code = {c: g.sort_values("report_date_str") for c, g in tdx.groupby("code")}
quality = pd.read_csv("data/cache/quality_snapshot.csv", dtype={"code": str})
quality_by_code = {c: g for c, g in quality.groupby("code")}
mkt = MarketData()

mktcap = {}
for c in codes:
    df = mkt.as_of(c, t_date)
    if len(df) >= 20:
        close = float(df["close"].iloc[-1])
        vol = float(df["volume"].mean()) if "volume" in df.columns else 1e6
        shares = None
        ctdx = tdx_by_code.get(c)
        if ctdx is not None and len(ctdx) > 0 and "total_shares" in ctdx.columns:
            shares = ctdx["total_shares"].dropna().iloc[-1]
        mktcap[c] = close * (shares if shares and shares > 0 else 1) / 1e8
mc_series = pd.Series(mktcap)
thr = mc_series.quantile(0.20)
liquid_excluded = {c for c in codes if c in mktcap and mktcap[c] < thr}

# 乖离率 >120%
dev_excluded = set()
for c in codes:
    df = mkt.as_of(c, t_date)
    if len(df) >= 200:
        close = df["close"]
        ma200 = close.rolling(200).mean().iloc[-1]
        last = close.iloc[-1]
        if ma200 > 0 and (last - ma200) / ma200 > 1.20:
            dev_excluded.add(c)

ind_map = dict(zip(pd.read_csv("data/cache/sw_stock_industry.csv", dtype={"code": str})["code"],
                   pd.read_csv("data/cache/sw_stock_industry.csv", dtype={"code": str})["sw1"]))

print(f"=== Feature Activation Impact（t_date={t_date}）===")
print(f"流动性剔除 {len(liquid_excluded)} 只:")
lc = pd.Series({c: mktcap[c] for c in liquid_excluded if c in mktcap})
print(f"  市值中位: {lc.median():.1f}亿 (全部候选市值中位 {mc_series.median():.1f}亿)")
inds = pd.Series([ind_map.get(c, '?') for c in liquid_excluded]).value_counts()
print(f"  行业 Top5: {dict(inds.head(5))}")
print(f"\n乖离率剔除 {len(dev_excluded)} 只:")
for c in sorted(dev_excluded)[:10]:
    df = mkt.as_of(c, t_date)
    close = df["close"]
    ma200 = close.rolling(200).mean().iloc[-1]
    last = close.iloc[-1]
    print(f"  {c} {ind_map.get(c,'?'):<6} 乖离={((last-ma200)/ma200):.0%} 市值={mktcap.get(c,float('nan')):.0f}亿")
