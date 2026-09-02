"""Step 5.3: 2026Q2 当前时点全市场研究扫描 (双雷达)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from loguru import logger

from growth_os.lifecycle_research import LifecycleResearchLayer, prewarm_financial_cache
from trade_calendar import get_t_date
from universe import get_universe
from industry import get_sw_industry
from valuation_filter import apply_valuation_filter

T_DATE = "20260901"  # 2026-09-01: 中报披露完毕后首个研究日
t_date = get_t_date(T_DATE)

u = get_universe(t_date)
ind = get_sw_industry()
codes = apply_valuation_filter(t_date, u["code"].tolist(), ind)
logger.info(f"候选池: {len(codes)} 只")

prewarm_financial_cache(t_date)
layer = LifecycleResearchLayer(ind_map=ind)
# 历史 RPS: 用最近 12 个月价格重算峰值 (日级近似, 供 L5 Layer1)
from pit.market import MarketData
import numpy as np
mkt = MarketData()

# 简化: L5 历史确认用 250 日内 RPS 峰值 (用截面分位的 60 日收益替代)
def hist_rps_peaks(codes, t_date, ind_map):
    """历史 RPS 峰值: 以过去 12 个月每 60 日窗口的行业内分位最大值为近似。"""
    from screener import compute_rps60
    from trade_calendar import get_trade_calendar
    cal = get_trade_calendar("20250101", t_date)
    dates = cal["trade_date"].tolist()
    # 采样 4 个历史时点
    peaks = {}
    for d in dates[::90][-4:]:
        try:
            r = compute_rps60(codes, d, ind_map)
            for c, v in r.items():
                peaks[c] = max(peaks.get(c, 0), v)
        except Exception:
            pass
    return peaks

hist_max = hist_rps_peaks(codes, t_date, ind)
logger.info(f"历史 RPS 峰值计算完成: {len(hist_max)} 只")

# 全候选池标注 (分批避免内存问题)
batch = 500
results = []
for i in range(0, len(codes), batch):
    sub = pd.DataFrame({"code": codes[i:i+batch]})
    out = layer.annotate(sub, t_date, hist_rps_max=hist_max)
    results.append(out)
    logger.info(f"批次 {i//batch+1}: 完成")

df = pd.concat(results, ignore_index=True)
os.makedirs("output", exist_ok=True)
df.to_csv("output/research_pool_20260901.csv", index=False, encoding="utf-8-sig")

# 双雷达输出
growth = df[df["radar"] == "growth_radar"].sort_values("research_priority")
recovery = df[df["radar"] == "recovery_radar"].sort_values("research_priority")
logger.info(f"Growth Radar: {len(growth)} 只 | Recovery Radar: {len(recovery)} 只")
print("=== 双雷达分布 ===")
print(df["research_stage"].value_counts().to_string())
print(f"\nGrowth Radar A级: {len(growth[growth['research_priority']=='A'])} 只")
print(f"Recovery Radar A级: {len(recovery[recovery['research_priority']=='A'])} 只")
print("已保存 output/research_pool_20260901.csv")
