"""增长持续性概率 — 将离散探针标签升级为连续概率。

probe_accuracy_study 证明纯财务探针是反向指标（3G0R=-9.6%）。
通过三层融合修正偏差：
  1. 产业周期先验（#4 宏观数据）
  2. 探针证据修正（4探针 ±10分）
  3. 财务趋势确认（营收/毛利率/ROIC 趋势 ±5分）

输出：0-100% 增长在未来4季度持续的概率。
"""
from __future__ import annotations


def compute_persistence_probability(
    code: str, t_date: str, industry_l3: str = None
) -> dict:
    """计算增长持续性概率（0-100%）。

    Returns:
        {"probability": 0-100, "label": str, "level": str,
         "prior": int, "probe_adj": int, "trend_adj": int}
    """
    prior = 50
    probe_adj = 0
    trend_adj = 0
    probe_details = {}
    trend_details = {}

    # ── Layer 1: 产业周期先验 ──
    try:
        from growth_os.industry_indicators import get_industry_cycle_signal
        cycle = get_industry_cycle_signal(t_date)
        prior = cycle.get("score", 50)
    except Exception:
        pass

    # ── Layer 2: 探针证据修正 ──
    try:
        from growth_os.growth_probes import run_all_probes
        probes = run_all_probes(code, t_date, industry_l3)
        for p in probes:
            level = p.get("level", "unknown")
            if level == "green":
                probe_adj += 10
                probe_details[p["name"]] = "+10"
            elif level == "red":
                probe_adj -= 10
                probe_details[p["name"]] = "-10"
            elif level == "yellow":
                probe_details[p["name"]] = "0"
            else:
                probe_details[p["name"]] = "N/A"
    except Exception:
        pass

    # ── Layer 3: 财务趋势确认 ──
    try:
        from growth_os.data import get_financial_snapshot, get_quarterly_series
        import pandas as pd

        snap = get_financial_snapshot(t_date)
        row = snap[snap["code"] == code]
        if not row.empty:
            row = row.iloc[0]

            # 营收增速
            rev_yoy = row.get("revenue_yoy")
            if rev_yoy is not None and not pd.isna(rev_yoy) and rev_yoy > 0:
                trend_adj += 5
                trend_details["revenue_yoy"] = f"+5 (增速{rev_yoy:.0f}%)"
            elif rev_yoy is not None and not pd.isna(rev_yoy):
                trend_details["revenue_yoy"] = f"0 (增速{rev_yoy:.0f}%)"

            # 毛利率趋势
            gm_series = get_quarterly_series(code, "gross_margin",
                                             n_quarters=8, t_date=t_date).dropna()
            if len(gm_series) >= 8:
                recent_gm = gm_series.iloc[-4:].mean()
                old_gm = gm_series.iloc[-8:-4].mean()
                if recent_gm > old_gm:
                    trend_adj += 5
                    trend_details["gross_margin"] = f"+5 (上升{recent_gm-old_gm:+.1f}pp)"
                elif recent_gm >= old_gm * 0.98:
                    trend_details["gross_margin"] = "0 (稳定)"
                else:
                    trend_details["gross_margin"] = f"0 (下降{recent_gm-old_gm:+.1f}pp)"

            # ROIC 趋势
            roic_series = get_quarterly_series(code, "roic",
                                                n_quarters=8, t_date=t_date).dropna()
            if len(roic_series) >= 8:
                recent_roic = roic_series.iloc[-4:].mean()
                old_roic = roic_series.iloc[-8:-4].mean()
                if recent_roic > old_roic:
                    trend_adj += 5
                    trend_details["roic"] = f"+5 (提升{recent_roic-old_roic:+.1f}pp)"
                elif recent_roic >= old_roic * 0.95:
                    trend_details["roic"] = "0 (平稳)"
                else:
                    trend_details["roic"] = f"0 (下滑{recent_roic-old_roic:+.1f}pp)"
    except Exception:
        pass

    # ── 最终概率 ──
    probability = max(0, min(100, prior + probe_adj + trend_adj))

    if probability >= 70:
        label = f"🟢 高持续性（{probability}%）— 增长大概率延续"
        level = "high"
    elif probability >= 40:
        label = f"🟡 中等持续性（{probability}%）— 需关注边际变化"
        level = "medium"
    else:
        label = f"🔴 低持续性（{probability}%）— 增长可能逆转"
        level = "low"

    return {
        "probability": probability,
        "label": label,
        "level": level,
        "prior": prior,
        "probe_adj": probe_adj,
        "trend_adj": trend_adj,
        "probe_details": probe_details,
        "trend_details": trend_details,
    }
