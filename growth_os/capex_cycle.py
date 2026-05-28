"""CAPEX 周期定位引擎 — 判断公司处于资本开支周期的哪个阶段。

四象限分类：
  扩张期: CAPEX↑ + 营收↑ — 健康扩产
  危险区: CAPEX↑ + 营收↓ — 产能过剩风险
  收缩期: CAPEX↓ + 营收↓ — 行业出清中
  复苏期: CAPEX↓ + 营收↑ — 产能利用率改善

v3.0: 新增 CAPEX/D&A 比（维护性 vs 扩张性）和深度趋势分析（二阶导+在建工程信号）。
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from loguru import logger

from growth_os.data import get_quarterly_series, get_financial_snapshot


def classify_capex_cycle(code: str, t_date: str) -> dict:
    """分类公司 CAPEX 周期阶段。

    Returns:
        {"phase": str, "label": str, "level": "green"|"yellow"|"red",
         "capex_growth": float, "rev_growth": float,
         "capex_rev_ratio": float, "detail": dict}
    """
    capex = get_quarterly_series(code, "capex_cash", n_quarters=8, t_date=t_date).dropna()
    rev = get_quarterly_series(code, "revenue_q", n_quarters=8, t_date=t_date).dropna()

    if len(capex) < 6 or len(rev) < 6:
        return {"phase": "unknown", "label": "⚪ CAPEX周期：数据不足", "level": "unknown",
                "capex_growth": None, "rev_growth": None, "capex_rev_ratio": None}

    capex_recent = capex.iloc[-4:].sum()
    capex_prior = capex.iloc[-8:-4].sum()
    rev_recent = rev.iloc[-4:].sum()
    rev_prior = rev.iloc[-8:-4].sum()

    if capex_prior <= 0 or rev_prior <= 0:
        return {"phase": "unknown", "label": "⚪ CAPEX周期：基期数据异常", "level": "unknown",
                "capex_growth": None, "rev_growth": None, "capex_rev_ratio": None}

    capex_growth = (capex_recent / capex_prior - 1) * 100
    rev_growth = (rev_recent / rev_prior - 1) * 100
    capex_rev_ratio = capex_recent / rev_recent * 100
    capex_rev_prior = capex_prior / rev_prior * 100

    # 四象限判定
    if capex_growth > 15 and rev_growth > 10:
        phase = "expansion"
        level = "green"
        label = f"🟢 扩张期（CAPEX+{capex_growth:.0f}%，营收+{rev_growth:.0f}%），产能健康扩张"
    elif capex_growth > 0 and rev_growth < -5:
        phase = "danger"
        level = "red"
        label = f"🔴 危险区（CAPEX+{capex_growth:.0f}%，营收{rev_growth:.0f}%），产能过剩风险"
    elif capex_growth < -10 and rev_growth < -5:
        phase = "contraction"
        level = "yellow"
        label = f"🟡 收缩期（CAPEX{rev_growth:.0f}%，营收{rev_growth:.0f}%），行业出清中"
    elif capex_growth < 0 and rev_growth > 5:
        phase = "recovery"
        level = "green"
        label = f"🟢 复苏期（CAPEX{capex_growth:.0f}%，营收+{rev_growth:.0f}%），产能利用率改善"
    elif abs(capex_growth) < 10 and abs(rev_growth) < 10:
        # TTM平稳但需检查单季是否已恶化
        rev_q = get_quarterly_series(code, "revenue_yoy", n_quarters=1, t_date=t_date).dropna()
        rev_latest = rev_q.iloc[-1] if len(rev_q) > 0 else rev_growth
        if rev_latest < -10:
            phase = "plateau_risky"
            level = "yellow"
            label = f"🟡 出清滞后（CAPEX{capex_growth:+.0f}%，营收TTM{rev_growth:+.0f}%/单季{rev_latest:.0f}%），资本开支未随营收收缩"
        else:
            phase = "plateau"
            level = "yellow"
            label = f"🟡 平台期（CAPEX{capex_growth:+.0f}%，营收{rev_growth:+.0f}%），资本开支平稳"
    elif capex_growth > 0 and rev_growth >= -5:
        phase = "mild_expansion"
        level = "yellow"
        label = f"🟡 温和扩张（CAPEX+{capex_growth:.0f}%，营收{rev_growth:+.0f}%）"
    else:
        phase = "plateau"
        level = "yellow"
        label = f"🟡 平台期（CAPEX{capex_growth:+.0f}%，营收{rev_growth:+.0f}%）"

    # 附加信息：CAPEX效率趋势
    if capex_rev_prior > 0:
        efficiency_delta = capex_rev_ratio - capex_rev_prior
        if efficiency_delta < -2:
            label += f"，资本效率改善(CAPEX/营收{capex_rev_prior:.0f}%→{capex_rev_ratio:.0f}%)"
        elif efficiency_delta > 3:
            label += f"，资本密集度上升(CAPEX/营收{capex_rev_prior:.0f}%→{capex_rev_ratio:.0f}%)"

    return {
        "phase": phase,
        "label": label,
        "level": level,
        "capex_growth": round(capex_growth, 1),
        "rev_growth": round(rev_growth, 1),
        "capex_rev_ratio": round(capex_rev_ratio, 1),
    }


# ═══════════════════════════════════════════════
# v3.0: CAPEX 深化
# ═══════════════════════════════════════════════

def classify_capex_intensity(code: str, t_date: str) -> dict:
    """CAPEX/Fixed_Assets 比 — 区分维护性投入 vs 扩张性投入。

    CAPEX/Fixed_Assets > 20% → 激进扩张
    10-20% → 适度扩张
    5-10% → 维持性投入
    < 5% → 投入不足

    Returns:
        {"level": "green"|"yellow"|"red"|"unknown",
         "label": str, "capex_fa_ratio": float}
    """
    capex = get_quarterly_series(code, "capex_cash", n_quarters=8, t_date=t_date).dropna()
    fixed = get_quarterly_series(code, "fixed_assets", n_quarters=4, t_date=t_date).dropna()

    if len(capex) < 4 or len(fixed) < 2:
        return {"level": "unknown", "label": "⚪ CAPEX强度：数据不足",
                "capex_fa_ratio": None}

    ttm_capex = capex.iloc[-4:].sum()
    avg_fixed = fixed.mean()

    if avg_fixed <= 0 or ttm_capex <= 0:
        return {"level": "unknown", "label": "⚪ CAPEX强度：数据异常",
                "capex_fa_ratio": None}

    ratio = ttm_capex / avg_fixed * 100  # as percentage

    if ratio > 20:
        level = "green"
        label = f"🟢 激进扩张（CAPEX/固定资产={ratio:.0f}%），大幅扩产中"
    elif ratio > 10:
        level = "green"
        label = f"🟢 适度扩张（CAPEX/固定资产={ratio:.0f}%），产能持续投入"
    elif ratio > 5:
        level = "yellow"
        label = f"🟡 维持性投入（CAPEX/固定资产={ratio:.0f}%），基本维持现有产能"
    else:
        level = "red"
        label = f"🔴 投入不足（CAPEX/固定资产={ratio:.0f}%），可能在吃老本"

    return {"level": level, "label": label, "capex_fa_ratio": round(ratio, 1)}


def analyze_capex_trend(code: str, t_date: str) -> dict:
    """CAPEX 深度趋势分析 — 二阶导 + 在建工程转化信号。

    Returns:
        {"capex_accelerating": bool,       # CAPEX增速本身在加速
         "construction_converting": bool,   # 在建工程→固定资产转化中
         "capacity_utilization_trend": str, # 产能利用率代理趋势
         "label": str}
    """
    capex = get_quarterly_series(code, "capex_cash", n_quarters=12, t_date=t_date).dropna()
    fixed = get_quarterly_series(code, "fixed_assets", n_quarters=12, t_date=t_date).dropna()
    cip = get_quarterly_series(code, "construction_in_progress",
                                n_quarters=12, t_date=t_date).dropna()
    rev = get_quarterly_series(code, "revenue_q", n_quarters=12, t_date=t_date).dropna()

    result = {"capex_accelerating": False, "construction_converting": False,
              "capacity_utilization_trend": "unknown", "label": ""}
    labels = []

    # 1. CAPEX 二阶导：近4季CAPEX增速 vs 前4季CAPEX增速
    if len(capex) >= 10:
        recent_4 = capex.iloc[-4:].sum()
        mid_4 = capex.iloc[-8:-4].sum()
        old_4 = capex.iloc[-12:-8].sum()
        if old_4 > 0 and mid_4 > 0:
            recent_growth = (recent_4 / mid_4 - 1) * 100
            prior_growth = (mid_4 / old_4 - 1) * 100
            if recent_growth > prior_growth + 10:
                result["capex_accelerating"] = True
                labels.append("CAPEX加速扩张")
            elif recent_growth < prior_growth - 10:
                labels.append("CAPEX增速放缓")

    # 2. 在建工程转化：CIP下降 + 固定资产上升 = 产能即将释放
    if len(cip) >= 8 and len(fixed) >= 8:
        cip_recent = cip.iloc[-4:].mean()
        cip_old = cip.iloc[-8:-4].mean()
        fixed_recent = fixed.iloc[-4:].mean()
        fixed_old = fixed.iloc[-8:-4].mean()
        if cip_recent < cip_old * 0.9 and fixed_recent > fixed_old:
            result["construction_converting"] = True
            labels.append("在建工程转固→产能即将释放")

    # 3. 产能利用率代理：revenue/fixed_assets 趋势
    if len(rev) >= 8 and len(fixed) >= 8 and fixed.iloc[-4:].mean() > 0:
        util_recent = rev.iloc[-4:].sum() / fixed.iloc[-4:].mean()
        util_old = rev.iloc[-8:-4].sum() / fixed.iloc[-8:-4].mean()
        if util_recent > util_old * 1.05:
            result["capacity_utilization_trend"] = "improving"
            labels.append("产能利用率改善")
        elif util_recent < util_old * 0.95:
            result["capacity_utilization_trend"] = "declining"
            labels.append("产能利用率下降")
        else:
            result["capacity_utilization_trend"] = "stable"

    if labels:
        result["label"] = "；".join(labels)
    else:
        result["label"] = "CAPEX趋势平稳，无显著信号"

    return result
