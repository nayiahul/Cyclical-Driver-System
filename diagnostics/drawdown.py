"""回撤归因 — 识别回撤期，拆解行业/因子贡献。

用法:
  from diagnostics.drawdown import analyze_drawdowns
  result = analyze_drawdowns(nav_series, daily_returns, industry_map)
"""
from collections import defaultdict

import numpy as np
import pandas as pd


def analyze_drawdowns(nav: pd.Series,
                      returns: pd.Series,
                      daily_holdings: list[dict] = None) -> dict:
    """
    Args:
        nav: 日度 NAV 序列
        returns: 日收益率序列
        daily_holdings: [{date, holdings: {code: shares}}, ...] 可选

    Returns:
        {
            "max_dd": float,
            "max_dd_start": str,
            "max_dd_end": str,
            "max_dd_duration": int,      # 交易日
            "max_dd_recovery": int,       # 恢复所需交易日
            "dd_episodes": [{start, end, depth, duration, recovery}],
            "monthly_dd": pd.Series,      # 月度回撤序列
        }
    """
    # 计算回撤序列
    cummax = nav.cummax()
    drawdown = (nav - cummax) / cummax

    # 找出最大回撤
    max_dd = drawdown.min()
    max_dd_end_idx = drawdown.idxmin()
    max_dd_end = str(max_dd_end_idx)[:10]

    # 回撤起点：最大值之后开始下跌的位置
    peak_idx = cummax[:max_dd_end_idx].idxmax()
    max_dd_start = str(peak_idx)[:10]

    # 回撤持续时间 (确保是 timestamp)
    end_ts = pd.Timestamp(max_dd_end_idx)
    start_ts = pd.Timestamp(peak_idx)
    duration = (end_ts - start_ts).days

    # 恢复时间：回到峰值需要的天数
    recovery = 0
    recovery_date = None
    for idx in drawdown.index[drawdown.index > max_dd_end_idx]:
        if nav[idx] >= cummax[max_dd_end_idx]:
            recovery = (idx - max_dd_end_idx).days
            recovery_date = str(idx)[:10]
            break

    # 识别所有显著回撤期 (>5%)
    episodes = []
    in_dd = False
    dd_start = None
    dd_peak = 0
    for idx, val in drawdown.items():
        if not in_dd and val < -0.05:
            in_dd = True
            dd_start = idx
            dd_peak = 0
        if in_dd:
            if val < dd_peak:
                dd_peak = val
            if val > -0.02:  # 恢复到2%以内视为结束
                episodes.append({
                    "start": str(dd_start)[:10],
                    "end": str(idx)[:10],
                    "depth": round(float(dd_peak), 4),
                    "duration": (idx - dd_start).days,
                })
                in_dd = False

    # 月度回撤
    monthly = drawdown.resample("ME").min()

    result = {
        "max_dd": round(float(max_dd), 4),
        "max_dd_start": max_dd_start,
        "max_dd_end": max_dd_end,
        "max_dd_duration": duration,
        "max_dd_recovery": recovery,
        "max_dd_recovery_date": recovery_date,
        "episodes": episodes,
        "monthly_dd": monthly,
    }

    # 如果有持仓数据，做行业归因
    if daily_holdings:
        industry_attribution = _attribute_dd_by_industry(
            nav, drawdown, daily_holdings, max_dd_end_idx, peak_idx
        )
        result["industry_attribution"] = industry_attribution

    return result


def _attribute_dd_by_industry(nav, drawdown, holdings, dd_end, dd_start):
    """简单行业归因：回撤期内各行业持仓收益贡献。"""
    # 这是粗略版本 — 需要每个调仓日的行业权重和区间收益来精确分解
    return {"note": "需要逐期持仓行业权重数据做精确分解"}


def summary_report(result: dict) -> str:
    """生成可读的回撤归因摘要。"""
    lines = []
    lines.append(f"最大回撤: {result['max_dd']:.2%}")
    lines.append(f"  起点: {result['max_dd_start']}")
    lines.append(f"  终点: {result['max_dd_end']}")
    lines.append(f"  持续: {result['max_dd_duration']} 天")
    if result.get("max_dd_recovery"):
        lines.append(f"  恢复: {result['max_dd_recovery']} 天 (至 {result.get('max_dd_recovery_date', '?')})")

    episodes = result.get("episodes", [])
    if episodes:
        lines.append(f"\n显著回撤期 (>5%): {len(episodes)} 次")
        for ep in sorted(episodes, key=lambda x: x["depth"])[:5]:
            lines.append(f"  {ep['start']} → {ep['end']}: {ep['depth']:.1%} ({ep['duration']}天)")

    monthly = result.get("monthly_dd")
    if monthly is not None and not monthly.empty:
        worst_months = monthly.nsmallest(5)
        lines.append(f"\n最差月份:")
        for dt, val in worst_months.items():
            lines.append(f"  {str(dt)[:7]}: {val:.1%}")

    return "\n".join(lines)
