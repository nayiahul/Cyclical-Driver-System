"""CAPEX 周期定位引擎 — 判断公司处于资本开支周期的哪个阶段。

四象限分类：
  扩张期: CAPEX↑ + 营收↑ — 健康扩产
  危险区: CAPEX↑ + 营收↓ — 产能过剩风险
  收缩期: CAPEX↓ + 营收↓ — 行业出清中
  复苏期: CAPEX↓ + 营收↑ — 产能利用率改善

不参与综合评分，作为探针5输出。
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from loguru import logger

from growth_os.data import get_quarterly_series


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
