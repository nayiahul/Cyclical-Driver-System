"""五层漏斗 — 成长股筛选核心引擎。

L1 排雷(Hard Gate) → L2 护城河 → L3 资本效率 → L4 行业校准 → L5 预期差
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass, field
from loguru import logger

from growth_os.config import (
    L1_THRESHOLDS, L2_SCORING, L3_SCORING, L5_SCORING,
    INDUSTRY_ADJUSTMENTS, EXCLUDED_INDUSTRIES_L1, CAPEX_HEAVY_INDUSTRIES,
    LifecycleStage,
)
from growth_os.data import (
    get_financial_snapshot, get_quarterly_series, get_price_data,
    get_pe_ttm, load_industry_map, load_tdx_financials, get_industry,
    compute_revenue_cagr_3y, compute_roic_ttm,
)
from growth_os.wacc import compute_wacc

# L1 红灯分级：绝对红灯(单灯淘汰) vs 条件红灯(需2灯淘汰)
ABSOLUTE_RED_KEYS = {
    "_error",                    # 无财务数据
    "goodwill_ratio",            # 商誉/净资产>30% — 并购地雷
    "inventory_structure",       # 产成品占比>70% — 滞销
    "rd_capitalization",         # 研发资本化率>50% — 虚增利润
    "subsidy_dependency",        # 政府补助占扣非利润>50% — 非经常性依赖
}

CONDITIONAL_RED_KEYS = {
    "revenue_cagr_3y",           # 营收3年CAGR过低 — 增长疲弱
    "yoy_truncated",             # 扣非/营收增速=500哨兵值 — 数据管道错误
    "yoy_cagr_divergence",       # 近期高增但3年CAGR低 — 周期恢复
    "profit_without_growth",     # 营收停滞利润暴增 — 伪成长
    "deducted_vs_revenue",       # 扣非增速跟不上营收 — 利润质量差
    "ocf_profit_ratio_3y",       # OCF/净利润低 — 现金含金量不足
    "high_leverage",             # 有息负债率>60% — 结构性财务风险
    "receivable_surge",          # 应收增速远超营收 — 需结合营收方向判断
    "inventory_surge",           # 存货增速>营收增速×阈值 — 需结合行业判断
    "cashflow_burn",             # 近3季OCF<0但利润>0 — 可能是扩张期
}


def run_funnel(
    code: str, t_date: str, industry_l3: str = None,
    lifecycle: LifecycleStage = None,
    l1_strict: bool = False,
    pct_table: dict = None,
) -> dict:
    """对单只股票执行五层漏斗检查。

    Args:
        l1_strict: True=条件红灯1项即淘汰（DEFENSE/CAUTION模式）。

    Returns:
        {
            "pass_l1": bool,          # 通过排雷
            "l1_red_flags": [str],    # 触发的红灯
            "l1_details": dict,       # 各项详情
            "score_l2": float,        # 护城河 0-10
            "l2_details": dict,
            "score_l3": float,        # 资本效率 0-10
            "l3_details": dict,
            "score_l4": float,        # 行业校准 0-10
            "l4_details": dict,
            "score_l5": float,        # 预期差 0-10
            "l5_details": dict,
        }
    """
    if industry_l3 is None:
        industry_l3 = get_industry(code)

    result = {
        "pass_l1": True,
        "l1_red_flags": [],
        "l1_details": {},
        "score_l2": np.nan,
        "l2_details": {},
        "score_l3": np.nan,
        "l3_details": {},
        "score_l4": np.nan,
        "l4_details": {},
        "score_l5": np.nan,
        "l5_details": {},
    }

    # ---- L1: 排雷 (二级红灯制) ----
    l1 = _check_l1(code, t_date, industry_l3)
    result["l1_details"] = l1

    all_red = [k for k, v in l1.items() if v.get("red", False)]
    absolute_reds = [k for k in all_red if k in ABSOLUTE_RED_KEYS]
    conditional_reds = [k for k in all_red if k in CONDITIONAL_RED_KEYS]
    # 未分类的新红灯默认视为条件红灯
    unclassified = [k for k in all_red if k not in ABSOLUTE_RED_KEYS and k not in CONDITIONAL_RED_KEYS]
    conditional_reds.extend(unclassified)

    result["l1_red_flags"] = all_red
    result["l1_absolute_reds"] = absolute_reds
    result["l1_conditional_reds"] = conditional_reds

    # 判定：l1_strict 时条件红灯 ≥1 即淘汰
    cond_kill_threshold = 1 if l1_strict else 2

    if absolute_reds:
        result["pass_l1"] = False
        result["l1_verdict"] = "kill_absolute"
    elif len(conditional_reds) >= cond_kill_threshold:
        result["pass_l1"] = False
        result["l1_verdict"] = "kill_conditional"
    elif len(conditional_reds) == 1 and not l1_strict:
        result["pass_l1"] = True
        result["l1_verdict"] = "review"
    else:
        result["pass_l1"] = True
        result["l1_verdict"] = "pass"

    # 即使 L1 未通过也继续跑完 L2-L5（报告需展示完整诊断）
    # L1 verdict 已在 report 中体现为"一票否决"

    # ---- L2: 护城河 ----
    l2 = _score_l2(code, t_date, industry_l3, pct_table)
    result["score_l2"] = l2.pop("total")
    result["l2_details"] = l2

    # ---- L3: 资本效率 ----
    l3 = _score_l3(code, t_date, industry_l3)
    result["score_l3"] = l3.pop("total")
    result["l3_details"] = l3

    # ---- L4: 行业校准 ----
    l4 = _score_l4(code, t_date, industry_l3)
    result["score_l4"] = l4.pop("total")
    result["l4_details"] = l4

    # ---- L5: 预期差 ----
    l5 = _score_l5(code, t_date, industry_l3)
    result["score_l5"] = l5.pop("total")
    result["l5_details"] = l5

    return result


# ============================================================
# L1: 排雷 (Hard Gate)
# ============================================================

def _check_l1(code: str, t_date: str, industry_l3: str) -> dict:
    """7 项排雷检查，每项返回 {value, red(bool), detail}。"""
    snap = get_financial_snapshot(t_date)
    row = snap[snap["code"] == code]
    if row.empty:
        return {"_error": {"red": True, "detail": "无财务数据"}}
    row = row.iloc[0]

    t = L1_THRESHOLDS
    result = {}

    # 0. 数据哨兵/极端值检测 — 哨兵=管道缺陷→条件红灯, 极端=低基数→仅警告
    BAD_YOY_SENTINELS = {500.0, 999.0, 9999.0}
    deducted_yoy_val = row.get("deducted_profit_yoy")
    revenue_yoy_raw = row.get("revenue_yoy")
    sentinel_flags = []
    extreme_flags = []
    def _is_sentinel(v):
        return any(abs(v - s) < 0.01 for s in BAD_YOY_SENTINELS)

    has_sentinel = False
    has_extreme = False
    if deducted_yoy_val is not None and not pd.isna(deducted_yoy_val):
        if _is_sentinel(deducted_yoy_val):
            sentinel_flags.append(f"扣非增速={deducted_yoy_val:.0f}%哨兵值→数据缺失占位")
            has_sentinel = True
        elif abs(deducted_yoy_val) > 300:
            extreme_flags.append(f"扣非增速={deducted_yoy_val:.0f}%极端(低基数)→g*不可外推")
            has_extreme = True
    if revenue_yoy_raw is not None and not pd.isna(revenue_yoy_raw):
        if _is_sentinel(revenue_yoy_raw):
            sentinel_flags.append(f"营收增速={revenue_yoy_raw:.0f}%哨兵值→数据缺失占位")
            has_sentinel = True
        elif abs(revenue_yoy_raw) > 300:
            extreme_flags.append(f"营收增速={revenue_yoy_raw:.0f}%极端→低基数爆炸")
            has_extreme = True

    result["yoy_truncated"] = {
        "value": None,
        "red": has_sentinel,
        "detail": "; ".join(sentinel_flags) if sentinel_flags else "增速值域正常",
    }
    result["_yoy_extreme"] = {
        "value": None,
        "red": False,  # 极端值不触发红灯，仅供报告/探针引用
        "detail": "; ".join(extreme_flags) if extreme_flags else "",
    }

    # 1. 营收3年CAGR — 用绝对营收TTM算3年CAGR
    rev_yoy = row.get("revenue_yoy")
    rev_yoy_val = rev_yoy if rev_yoy is not None and not pd.isna(rev_yoy) else 0
    cagr_3y = compute_revenue_cagr_3y(code, t_date)
    result["revenue_cagr_3y"] = {
        "value": round(cagr_3y, 1) if cagr_3y else None,
        "red": cagr_3y is not None and cagr_3y < t["revenue_cagr_3y_min"],
        "detail": f"营收3年CAGR={cagr_3y:.1f}%" if cagr_3y else "无足够数据",
    }

    # 1b. yoy-cagr背离检测 — 近期高增但长期萎缩→周期恢复而非成长
    cagr_val = cagr_3y if cagr_3y else 0
    yoy_cagr_divergence = False
    yoy_cagr_detail = ""
    if rev_yoy_val and cagr_3y is not None:
        if rev_yoy_val > 50 and cagr_val < 10:
            yoy_cagr_divergence = True
            yoy_cagr_detail = f"近期高增({rev_yoy_val:.0f}%)但3年CAGR低({cagr_val:.1f}%)→疑似周期恢复"
        elif rev_yoy_val > 30 and cagr_val < 0:
            yoy_cagr_divergence = True
            yoy_cagr_detail = f"近期高增({rev_yoy_val:.0f}%)但3年萎缩({cagr_val:.1f}%)→确认周期恢复"
    result["yoy_cagr_divergence"] = {
        "value": None, "red": yoy_cagr_divergence,
        "detail": yoy_cagr_detail or "增速趋势一致",
    }

    # 2. 扣非增速 vs 营收增速
    deducted_yoy = row.get("deducted_profit_yoy")
    deduct_val = deducted_yoy if deducted_yoy is not None and not pd.isna(deducted_yoy) else 0
    result["deducted_vs_revenue"] = {
        "value": {"deducted": round(deduct_val, 1), "revenue": round(rev_yoy_val, 1)},
        "red": deduct_val < rev_yoy_val * t["deducted_vs_revenue_min_ratio"],
        "detail": f"扣非{deduct_val:.1f}% vs 营收{rev_yoy_val:.1f}%",
    }

    # 3. OCF/净利润 3年均值
    ocf_series = get_quarterly_series(
        code, "operating_cash_flow", n_quarters=24, t_date=t_date
    ).dropna()
    profit_series = get_quarterly_series(
        code, "deducted_profit_q", n_quarters=24, t_date=t_date
    ).dropna()

    ocf_profit_ratio = None
    if len(ocf_series) >= 4 and len(profit_series) >= 4:
        common = ocf_series.index.intersection(profit_series.index)
        if len(common) >= 4:
            ocf_sum = ocf_series.loc[common].sum()
            profit_sum = abs(profit_series.loc[common].sum())
            if profit_sum > 0:
                ocf_profit_ratio = ocf_sum / profit_sum
    result["ocf_profit_ratio_3y"] = {
        "value": round(ocf_profit_ratio, 2) if ocf_profit_ratio else None,
        "red": ocf_profit_ratio is not None and (
            ocf_profit_ratio < 0  # OCF为负→现金无法覆盖利润，强制红灯
            or ocf_profit_ratio < t["ocf_profit_ratio_3y_min"]
        ),
        "detail": f"OCF/净利润(3年)={ocf_profit_ratio:.2f}" if ocf_profit_ratio else "数据不足",
    }

    # v2.5: OCF负值联动 — 非高研发行业OCF<0自动叠加第二条件红灯
    # 高研发行业(rd>30%, 如Biotech) OCF为负是行业常态，仅review不kill
    rd_val = row.get("rd_expense", 0) or 0
    rev_val = row.get("revenue", 0) or 1
    rd_ratio = rd_val / rev_val * 100 if rev_val > 0 else 0
    result["ocf_negative_cascade"] = {
        "value": None,
        "red": (ocf_profit_ratio is not None and ocf_profit_ratio < 0 and rd_ratio < 30),
        "detail": f"OCF<0且rd={rd_ratio:.1f}%{'<30%→非高研发→叠加淘汰' if rd_ratio < 30 else '≥30%→高研发豁免'}",
    }

    # 3b. profit_without_growth — 营收停滞但利润暴增→伪成长
    profit_wo_growth = False
    if rev_yoy_val < 5 and deduct_val > 50:
        ocf_ok = ocf_profit_ratio is not None and ocf_profit_ratio >= 1.0
        if not ocf_ok:
            profit_wo_growth = True
    result["profit_without_growth"] = {
        "value": None,
        "red": profit_wo_growth,
        "detail": (f"营收+{rev_yoy_val:.1f}%但扣非+{deduct_val:.0f}%"
                   f"{'→利润暴增无增长(OCF未验证)' if profit_wo_growth else ''}"),
    }

    # 4. 应收飙升
    notes_recv_series = get_quarterly_series(
        code, "notes_and_acct_receivable", n_quarters=8, t_date=t_date
    ).dropna()
    recv_surge = False
    if len(notes_recv_series) >= 2:
        recent_recv = notes_recv_series.iloc[-1]
        prev_recv = notes_recv_series.iloc[-2]
        # 应收占营收>1%时才检查（避免低基数伪信号）
        revenue_recent = row.get("revenue", 0) or 0
        if prev_recv > 0 and recent_recv / max(revenue_recent, 1) > 0.01:
            recv_growth = (recent_recv / prev_recv - 1)
            recv_pct = recv_growth * 100
            if rev_yoy_val > 0:
                # 正增长：应收增速不应远超营收增速
                recv_surge = recv_pct > rev_yoy_val * t["receivable_surge_ratio"]
            else:
                # 负增长：应收降幅应跟上营收降幅，否则=赊销撑收入
                recv_surge = (recv_pct - rev_yoy_val) > 15
            result["receivable_surge"] = {
                "value": round(recv_pct, 1),
                "red": recv_surge,
                "detail": f"应收增速{recv_pct:.1f}% vs 营收增速{rev_yoy_val:.1f}%",
            }
        else:
            result["receivable_surge"] = {"value": None, "red": False,
                                          "detail": "应收/营收<1%，跳过"}
    else:
        result["receivable_surge"] = {"value": None, "red": False, "detail": "数据不足"}

    # 5. 存货飙升
    inv_series = get_quarterly_series(
        code, "inventory", n_quarters=8, t_date=t_date
    ).dropna()
    inv_surge = False
    if len(inv_series) >= 2:
        recent_inv = inv_series.iloc[-1]
        prev_inv = inv_series.iloc[-2]
        # 存货/总资产>3%时才检查（同样避免低基数）
        total_assets_v = row.get("total_assets", 0) or 0
        if prev_inv > 0 and recent_inv / max(total_assets_v, 1) > 0.03:
            inv_growth = (recent_inv / prev_inv - 1)
            inv_threshold = t["inventory_surge_ratio"]
            if industry_l3 in CAPEX_HEAVY_INDUSTRIES:
                inv_threshold = 2.0
            if rev_yoy_val > 0:
                inv_surge = inv_growth > rev_yoy_val / 100 * inv_threshold
            result["inventory_surge"] = {
                "value": round(inv_growth * 100, 1),
                "red": inv_surge,
                "detail": f"存货增速{inv_growth*100:.1f}% (阈值{inv_threshold}x营收增速)",
            }
        else:
            result["inventory_surge"] = {"value": None, "red": False,
                                         "detail": "存货/总资产<3%，跳过"}
    else:
        result["inventory_surge"] = {"value": None, "red": False, "detail": "数据不足"}

    # 6. 商誉/净资产
    goodwill = row.get("goodwill")
    equity = row.get("equity_parent") or row.get("total_assets", 0) - (
        row.get("short_term_loan", 0) or 0 + (row.get("long_term_loan", 0) or 0)
    )
    if goodwill is not None and not pd.isna(goodwill) and equity > 0:
        gw_ratio = goodwill / equity
        result["goodwill_ratio"] = {
            "value": round(gw_ratio, 3),
            "red": gw_ratio > t["goodwill_equity_max"],
            "detail": f"商誉/净资产={gw_ratio:.1%}",
        }
    else:
        result["goodwill_ratio"] = {"value": None, "red": False, "detail": "数据不足"}

    # 7. 现金流燃烧（利润为正但OCF为负）
    ocf_recent = get_quarterly_series(
        code, "operating_cash_flow", n_quarters=3, t_date=t_date
    ).dropna()
    profit_q = row.get("deducted_profit_q") or 0
    cash_burn = False
    if len(ocf_recent) >= 3:
        cash_burn = (ocf_recent.sum() < 0 and profit_q > 0)
    result["cashflow_burn"] = {
        "value": round(ocf_recent.sum() / 1e8, 1) if len(ocf_recent) >= 3 else None,
        "red": cash_burn,
        "detail": f"近3季OCF={ocf_recent.sum()/1e8:.1f}亿, 利润Q={profit_q/1e8:.1f}亿",
    }

    # 8-10. PDF 附录数据增强排雷（有数据时才检查）
    try:
        from growth_os.pdf_data import (
            get_inventory_signal, get_rd_quality_signal, get_subsidy_signal)
        # 8. 存货结构
        inv_signal = get_inventory_signal(code)
        if inv_signal.get("finished_pct") is not None:
            result["inventory_structure"] = {
                "value": f"产成品{inv_signal['finished_pct']:.0f}%",
                "red": inv_signal.get("severity") == "yellow" and inv_signal.get("finished_pct", 0) > 70,
                "detail": inv_signal.get("detail", ""),
            }
        # 9. 研发资本化率
        rd_signal = get_rd_quality_signal(code)
        if rd_signal.get("capitalization_rate") is not None:
            result["rd_capitalization"] = {
                "value": f"{rd_signal['capitalization_rate']:.0f}%",
                "red": rd_signal.get("severity") == "red",
                "detail": rd_signal.get("detail", ""),
            }
        # 10. 政府补助依赖
        deducted_q = row.get("deducted_profit_q") or 0
        sub_signal = get_subsidy_signal(code, deducted_q)
        if sub_signal.get("subsidy_to_profit") is not None:
            result["subsidy_dependency"] = {
                "value": f"{sub_signal['subsidy_to_profit']:.0f}%",
                "red": sub_signal.get("severity") == "red",
                "detail": sub_signal.get("detail", ""),
            }
    except ImportError:
        pass

    # v2.5: 高负债检测 — debt_ratio>60%→条件红灯
    debt_ratio_val = row.get("interest_bearing_debt_ratio")
    result["high_leverage"] = {
        "value": round(debt_ratio_val, 1) if debt_ratio_val is not None and not pd.isna(debt_ratio_val) else None,
        "red": debt_ratio_val is not None and not pd.isna(debt_ratio_val) and debt_ratio_val > 60,
        "detail": f"有息负债率={debt_ratio_val:.0f}%" if debt_ratio_val is not None and not pd.isna(debt_ratio_val) else "数据不足",
    }

    return result


# ============================================================
# L2: 护城河 (0-10)
# ============================================================

def _score_l2(code: str, t_date: str, industry_l3: str, pct_table: dict = None) -> dict:
    s = L2_SCORING
    result = {"total": 0.0}
    max_score = s["l2_max_score"]
    snap = get_financial_snapshot(t_date)
    row = snap[snap["code"] == code]
    if row.empty:
        return result
    row = row.iloc[0]

    # 1. 毛利率趋势 (0-3) — v3.0: 趋势幅度+行业相对水平双维度
    import math
    gm_series = get_quarterly_series(
        code, "gross_margin", n_quarters=12, t_date=t_date
    ).dropna()
    if len(gm_series) >= 8:
        recent_gm = gm_series.iloc[-4:].mean()
        old_gm = gm_series.iloc[-8:-4].mean()
        gm_delta = recent_gm - old_gm

        # A: 趋势幅度 (0-1.5)
        score_trend = round(1.5 / (1 + math.exp(-0.5 * gm_delta)), 1)
        if gm_delta > 2:
            gm_label = "上升"
        elif gm_delta > -2:
            gm_label = "稳定"
        else:
            gm_label = "下降"

        # B: 行业相对水平 (0-1.5) — GM在同行中越高越好
        # v3.0 Sprint 6: 用预计算分位表替代 O(n²) 循环
        score_level = 0.0
        if pct_table:
            from growth_os.industry_percentile import get_pct
            pct = get_pct(pct_table, industry_l3, "gross_margin", code)
            score_level = round(1.5 * pct, 1)
            if pct > 0.8: gm_label += "(行业顶尖)"
            elif pct > 0.5: gm_label += "(行业领先)"
        else:
            try:
                same_ind = snap[snap["code"].apply(lambda c: get_industry(c) == industry_l3)]
                if len(same_ind) >= 5:
                    gm_vals = [v for v in same_ind["gross_margin"] if not pd.isna(v)]
                    gm_vals.sort()
                    rank = sum(1 for v in gm_vals if v < recent_gm)
                    pct = rank / len(gm_vals)
                    score_level = round(1.5 * pct, 1)
                    if pct > 0.8: gm_label += "(行业顶尖)"
                    elif pct > 0.5: gm_label += "(行业领先)"
            except Exception:
                pass

        gm_score = min(score_trend + score_level, s["gross_margin_up_weight"])
        result["gross_margin_trend"] = {"score": round(gm_score, 1), "label": gm_label,
                                        "recent": round(recent_gm, 1)}
    else:
        result["gross_margin_trend"] = {"score": 0, "label": "数据不足"}

    # 2. 费用率杠杆 (0-2)
    # (销售+管理)费用率随规模摊薄
    selling_series = get_quarterly_series(code, "selling_expense", n_quarters=8, t_date=t_date)
    admin_series = get_quarterly_series(code, "admin_expense", n_quarters=8, t_date=t_date)
    revenue_q_series = get_quarterly_series(code, "revenue_q", n_quarters=8, t_date=t_date)

    # 提前获取研发强度和营收增速，供 P1-3 门槛判断
    rd = row.get("rd_expense", 0) or 0
    revenue = row.get("revenue", 0) or 0
    rd_ratio_val = rd / revenue * 100 if revenue > 0 else 0
    rev_yoy_val = row.get("revenue_yoy")
    rev_yoy_val = rev_yoy_val if rev_yoy_val is not None and not pd.isna(rev_yoy_val) else 0

    if (len(selling_series.dropna()) >= 4 and len(admin_series.dropna()) >= 4
            and len(revenue_q_series.dropna()) >= 4):
        recent_rev = revenue_q_series.iloc[-4:].sum()
        old_rev = revenue_q_series.iloc[-8:-4].sum()
        if old_rev > 0:
            recent_expense_ratio = (selling_series.iloc[-4:].sum() +
                                    admin_series.iloc[-4:].sum()) / recent_rev * 100
            old_expense_ratio = (selling_series.iloc[-8:-4].sum() +
                                 admin_series.iloc[-8:-4].sum()) / old_rev * 100
            expense_delta = recent_expense_ratio - old_expense_ratio

            # v3.0: 行业相对费用率 — 绝对值在行业内的位置是主区分力
            import math
            cagr3_val = row.get("revenue_cagr_3y") or 0
            gm_label = result.get("gross_margin_trend", {}).get("label", "")
            has_rd_conversion = (gm_label == "上升" or (cagr3_val is not None and cagr3_val > 20))
            is_high_rd = rd_ratio_val > 8

            # A: 费用率行业相对水平 (0-1.0) — v3.0: expense_ratio分位(越低越好)
            score_a = 0.5  # default
            exp_label_a = ""
            if pct_table:
                from growth_os.industry_percentile import get_pct
                exp_pct = get_pct(pct_table, industry_l3, "expense_ratio", code)
                score_a = round(1.0 * exp_pct, 1)
                if exp_pct > 0.8:   exp_label_a = "行业顶尖"
                elif exp_pct > 0.6: exp_label_a = "行业领先"
                elif exp_pct > 0.4: exp_label_a = "行业中位"
                else:               exp_label_a = "行业偏高"
            else:
                try:
                    snap_all = get_financial_snapshot(t_date)
                    same_ind = snap_all[snap_all["code"].apply(
                        lambda c: get_industry(c) == industry_l3
                    )]
                    if len(same_ind) >= 5:
                        peers_ratios = []
                        for _, peer in same_ind.iterrows():
                            p_sell = peer.get("selling_expense", 0) or 0
                            p_admin = peer.get("admin_expense", 0) or 0
                            p_rev = peer.get("revenue", 0) or 1
                            peers_ratios.append((p_sell + p_admin) / p_rev * 100)
                        peers_ratios.sort()
                        n_peers = len(peers_ratios)
                        rank = sum(1 for r in peers_ratios if r < recent_expense_ratio)
                        pct = rank / n_peers
                        score_a = round(1.0 * (1 - pct), 1)
                        if pct < 0.2:  exp_label_a = "行业顶尖"
                        elif pct < 0.4: exp_label_a = "行业领先"
                        elif pct < 0.6: exp_label_a = "行业中位"
                        else:           exp_label_a = "行业偏高"
                except Exception:
                    pass

            # B: 费用率趋势 (0-0.5) — 变化幅度sigmoid
            adj_delta = expense_delta
            if is_high_rd and has_rd_conversion and rev_yoy_val > 10:
                adj_delta = expense_delta - 2.0  # 高研发容忍2pp
            score_b = round(0.5 / (1 + math.exp(0.5 * adj_delta)), 1)

            # 合并
            exp_score = min(score_a + score_b, s["expense_leverage_weight"])
            exp_score = round(max(exp_score, 0.1), 1)
            exp_label = f"{exp_label_a}({recent_expense_ratio:.0f}%)"
            if adj_delta < -3: exp_label += "↓改善"
            elif adj_delta > 3: exp_label += "↑恶化"

            result["expense_leverage"] = {"score": exp_score, "label": exp_label,
                                          "recent": round(recent_expense_ratio, 1)}
        else:
            result["expense_leverage"] = {"score": 0, "label": "数据不足"}
    else:
        result["expense_leverage"] = {"score": 0, "label": "数据不足"}

    # 3. 研发强度 (0-2) — v3.0: 行业分位替代绝对阈值
    rd = row.get("rd_expense", 0) or 0
    revenue = row.get("revenue", 0) or 0
    if revenue > 0:
        rd_ratio = rd / revenue * 100
        if pct_table:
            from growth_os.industry_percentile import get_pct
            rd_pct = get_pct(pct_table, industry_l3, "rd_intensity", code)
            if rd_pct > 0.8:
                result["rd_intensity"] = {"score": s["rd_intensity_weight"],
                                          "label": f"高研发({rd_ratio:.1f}%,p{rd_pct:.0%})"}
            elif rd_pct > 0.5:
                result["rd_intensity"] = {"score": s["rd_intensity_weight"] / 2,
                                          "label": f"中等研发({rd_ratio:.1f}%,p{rd_pct:.0%})"}
            else:
                result["rd_intensity"] = {"score": 0, "label": f"低研发({rd_ratio:.1f}%,p{rd_pct:.0%})"}
        else:
            adj = INDUSTRY_ADJUSTMENTS.get(industry_l3, {})
            rd_high = adj.get("rd_intensity_high", 8.0)
            if rd_ratio > rd_high:
                result["rd_intensity"] = {"score": s["rd_intensity_weight"],
                                          "label": f"高研发({rd_ratio:.1f}%)"}
            elif rd_ratio > rd_high * 0.5:
                result["rd_intensity"] = {"score": s["rd_intensity_weight"] / 2,
                                          "label": f"中等研发({rd_ratio:.1f}%)"}
            else:
                result["rd_intensity"] = {"score": 0, "label": f"低研发({rd_ratio:.1f}%)"}
    else:
        result["rd_intensity"] = {"score": 0, "label": "数据不足"}

    # 4. 合同负债领先 (0-2) — v3.0: 行业分位增强
    contract_series = get_quarterly_series(
        code, "contract_liabilities", n_quarters=8, t_date=t_date
    ).dropna()
    if len(contract_series) >= 4:
        recent_contract = contract_series.iloc[-4:].mean()
        old_contract = contract_series.iloc[-8:-4].mean()
        if old_contract > 0:
            contract_growth = (recent_contract / old_contract - 1) * 100
            rev_yoy_val = row.get("revenue_yoy") or 0
            adj_contract_weight = s["contract_liab_weight"]
            adj = INDUSTRY_ADJUSTMENTS.get(industry_l3, {})
            if adj.get("advance_receipts_weight"):
                adj_contract_weight *= adj["advance_receipts_weight"]
            if contract_growth > rev_yoy_val:
                score = min(adj_contract_weight, max_score - result["total"])
                result["contract_liabilities"] = {
                    "score": score,
                    "label": f"领先: 合同负债+{contract_growth:.1f}% > 营收+{rev_yoy_val:.1f}%"
                }
            elif contract_growth > 0:
                # v3.0: 行业分位增强 — top20%合同负债比给额外加分
                cl_bonus = 0
                if pct_table:
                    from growth_os.industry_percentile import get_pct
                    cl_pct = get_pct(pct_table, industry_l3, "contract_liab_ratio", code)
                    if cl_pct > 0.8:
                        cl_bonus = 0.3
                result["contract_liabilities"] = {
                    "score": adj_contract_weight / 2 + cl_bonus,
                    "label": f"同步: 合同负债+{contract_growth:.1f}%"
                }
            else:
                result["contract_liabilities"] = {
                    "score": 0, "label": f"下降: 合同负债{contract_growth:.1f}%"
                }
        else:
            result["contract_liabilities"] = {"score": 0, "label": "数据不足"}
    else:
        result["contract_liabilities"] = {"score": 0, "label": "数据不足"}

    # 5. 营收二阶导数 (0-1)
    rev_yoy_series = get_quarterly_series(
        code, "revenue_yoy", n_quarters=6, t_date=t_date
    ).dropna()
    if len(rev_yoy_series) >= 4:
        consec_up = 0
        for i in range(1, min(4, len(rev_yoy_series))):
            if rev_yoy_series.iloc[-i] > rev_yoy_series.iloc[-(i+1)]:
                consec_up += 1
        if consec_up >= 2:
            result["revenue_acceleration"] = {"score": s["revenue_accel_weight"],
                                              "label": f"加速(连续{consec_up}季环比提升)"}
        elif consec_up == 1:
            result["revenue_acceleration"] = {"score": s["revenue_accel_weight"] / 2,
                                              "label": "边际改善"}
        else:
            result["revenue_acceleration"] = {"score": 0, "label": "减速"}
    else:
        result["revenue_acceleration"] = {"score": 0, "label": "数据不足"}

    # 6. 高毛利业务占比 (0-1, PDF数据增强)
    try:
        from growth_os.pdf_data import get_cached_pdf_data
        pdf = get_cached_pdf_data(code)
        if pdf and pdf.get("high_gm_segment_pct") is not None:
            high_pct = pdf["high_gm_segment_pct"]
            if high_pct > 50:
                result["business_upgrade"] = {"score": 1.0,
                    "label": f"高毛利业务{high_pct:.0f}%（结构升级）"}
            elif high_pct > 30:
                result["business_upgrade"] = {"score": 0.5,
                    "label": f"高毛利业务{high_pct:.0f}%"}
    except ImportError:
        pass

    # 合计
    result["total"] = round(min(
        sum(v["score"] for k, v in result.items() if k != "total"
    ), max_score), 1)

    # v3.0: 高研发无转化→L2封顶8.5 (防止"研发豁免"通胀)
    if is_high_rd and not has_rd_conversion:
        result["total"] = min(result["total"], 8.5)

    return result


# ============================================================
# L3: 资本效率 (0-10)
# ============================================================

def _score_l3(code: str, t_date: str, industry_l3: str) -> dict:
    s = L3_SCORING
    max_score = s["l3_max_score"]
    result = {"total": 0.0}
    snap = get_financial_snapshot(t_date)
    row = snap[snap["code"] == code]
    if row.empty:
        return result
    row = row.iloc[0]

    # 1. ROIC vs WACC (0-4) — 优先使用 TTM ROIC
    roic_ttm = compute_roic_ttm(code, t_date)
    roic = roic_ttm if roic_ttm is not None else row.get("roic")
    roic_source = "TTM" if roic_ttm is not None else "快照"
    wacc = compute_wacc(code, t_date)
    if roic is not None and not pd.isna(roic):
        if wacc is not None:
            spread = roic - wacc
            result["roic_vs_wacc"] = {
                "value": {"roic": round(roic, 1), "wacc": round(wacc, 1),
                          "spread": round(spread, 1),
                          "roic_ttm": roic_ttm is not None},
                "label": f"ROIC(TTM{roic:.1f}%) vs WACC({wacc:.1f}%)",
            }
            # v3.0: 绝对利差Sigmoid(0-4子分制) — 中段3%为拐点,ROIC≤WACC硬地板
            # spread=0→1.0, 3%→2.5, 6%→3.2, 10%→3.7, 15%+→~4.0
            import math
            if spread <= 0:
                sigmoid = 1.0  # ROIC≤WACC: 硬地板
            else:
                sigmoid = 1.0 + 3.0 / (1 + math.exp(-0.3 * (spread - 3.0)))
            result["roic_vs_wacc"]["score"] = round(sigmoid, 1)
            if sigmoid > 3.5:
                result["roic_vs_wacc"]["label"] += f" >> 卓越(利差{spread:.1f}%)"
            elif sigmoid > 2.5:
                result["roic_vs_wacc"]["label"] += f" > 良好(利差{spread:.1f}%)"
            elif sigmoid > 1.5:
                result["roic_vs_wacc"]["label"] += f" > 及格(利差{spread:.1f}%)"
            else:
                result["roic_vs_wacc"]["label"] += f" < 毁灭价值(利差{spread:.1f}%)"
        else:
            # WACC 不可用，回退到绝对阈值：ROIC > 10% 优秀, > 5% 及格
            result["roic_vs_wacc"] = {
                "value": {"roic": round(roic, 1), "wacc": None, "spread": None,
                          "roic_ttm": roic_ttm is not None},
                "label": f"ROIC(TTM{roic:.1f}%) (WACC不可算)",
            }
            if roic > 10:
                result["roic_vs_wacc"]["score"] = 3.0
                result["roic_vs_wacc"]["label"] += " — 绝对值优秀"
            elif roic > 5:
                result["roic_vs_wacc"]["score"] = 1.5
                result["roic_vs_wacc"]["label"] += " — 绝对值及格"
            elif roic > 0:
                result["roic_vs_wacc"]["score"] = 0.5
                result["roic_vs_wacc"]["label"] += " — 勉强为正"
            else:
                result["roic_vs_wacc"]["score"] = 0
                result["roic_vs_wacc"]["label"] += " — 为负"
    else:
        result["roic_vs_wacc"] = {"score": 0, "label": "ROIC数据缺失",
                                  "value": {"roic": None, "wacc": None, "spread": None}}

    # ROIC单季异常检测：最新季度ROIC vs 近4季均值
    # 注：这不是真正的增量ROIC(ΔNOPAT/ΔIC)，而是单季偏离度预警
    if roic is not None and not pd.isna(roic):
        roic_q = get_quarterly_series(code, "roic", n_quarters=4, t_date=t_date).dropna()
        if len(roic_q) >= 2:
            roic_latest = roic_q.iloc[-1]
            roic_recent_avg = roic_q.mean()
            if roic_recent_avg > 2 and roic_latest < roic_recent_avg * 0.4:
                result["roic_single_q_anomaly"] = {
                    "label": f"⚠️ ROIC单季异常：最新季度{roic_latest:.1f}%远低于近4季均值{roic_recent_avg:.1f}%，需观察是否为一次性冲击或趋势反转",
                    "negative": True,
                }

    # 2. ROIC 趋势 (0-2) — 同比对比(同期)，避免季节性误判
    roic_series = get_quarterly_series(
        code, "roic", n_quarters=16, t_date=t_date
    ).dropna()
    if len(roic_series) >= 8:
        # 同期对比: 最近4季 vs 去年同期4季 (而非连续4季 vs 前4季)
        dates = [str(d) for d in roic_series.index]
        fy_current = [v for d, v in zip(dates, roic_series.values) if "1231" in d]
        if len(fy_current) >= 2:
            current_fy = fy_current[-1]
            prior_fy = fy_current[-2]
            if current_fy > prior_fy:
                result["roic_trend"] = {"score": 2.0,
                    "label": f"ROIC提升(年度{prior_fy:.1f}%→{current_fy:.1f}%)"}
            elif current_fy >= prior_fy * 0.9:
                result["roic_trend"] = {"score": 1.0,
                    "label": f"ROIC平稳(年度{prior_fy:.1f}%→{current_fy:.1f}%)"}
            else:
                result["roic_trend"] = {"score": 0,
                    "label": f"ROIC下滑(年度{prior_fy:.1f}%→{current_fy:.1f}%)"}
        else:
            # 无足够FY数据，回退到连续4季对比
            recent = roic_series.iloc[-4:].mean()
            old = roic_series.iloc[-8:-4].mean()
            if recent > old:
                result["roic_trend"] = {"score": 2.0,
                    "label": f"ROIC提升(近4季均值{old:.1f}%→{recent:.1f}%)"}
            elif recent >= old * 0.9:
                result["roic_trend"] = {"score": 1.0, "label": "ROIC平稳"}
            else:
                result["roic_trend"] = {"score": 0,
                    "label": f"ROIC下滑({old:.1f}→{recent:.1f})"}
    else:
        result["roic_trend"] = {"score": 0, "label": "数据不足"}

    # ROIC趋势分条件激活：绝对值<WACC时，趋势改善只给安慰分
    if (result["roic_trend"].get("score", 0) > 0
            and result.get("roic_vs_wacc", {}).get("score", 1) == 0
            and "数据不足" not in result["roic_trend"].get("label", "")):
        result["roic_trend"]["score"] = round(result["roic_trend"]["score"] * 0.3, 1)
        result["roic_trend"]["label"] += "（ROIC<WACC，趋势改善意义有限）"

    # 3. ROE质量 / 杜邦 (0-2)
    roe = row.get("roe")
    net_margin = row.get("net_margin")
    asset_turnover = row.get("total_asset_turnover")
    equity_mult = row.get("equity_multiplier")
    if roe is not None and not pd.isna(roe):
        if roe > s["roe_excellent"]:
            roe_score = 2.0
            roe_label = f"优秀(ROE={roe:.1f}%)"
        elif roe > s["roe_good"]:
            roe_score = 1.0
            roe_label = f"良好(ROE={roe:.1f}%)"
        else:
            roe_score = 0
            roe_label = f"偏低(ROE={roe:.1f}%)"

        # 降权：高杠杆驱动
        if equity_mult is not None and not pd.isna(equity_mult) and equity_mult > 5:
            roe_score *= 0.5
            roe_label += " [高杠杆]"
        result["roe_quality"] = {"score": roe_score, "label": roe_label,
                                 "value": round(roe, 1)}
    else:
        result["roe_quality"] = {"score": 0, "label": "数据不足"}

    # 4. FCF 趋势 (0-1)
    fcf = row.get("fcff_per_share")
    if fcf is not None and not pd.isna(fcf) and fcf > 0:
        result["fcf_trend"] = {"score": 1.0, "label": f"FCF正({fcf:.2f}元/股)"}
    elif fcf is not None and not pd.isna(fcf):
        result["fcf_trend"] = {"score": 0, "label": f"FCF负({fcf:.2f}元/股)"}
    else:
        result["fcf_trend"] = {"score": 0, "label": "数据不足"}

    # 5. 债务安全 (0-1)
    debt_ratio = row.get("interest_bearing_debt_ratio")
    interest_cov = row.get("interest_coverage")
    debt_ok = True
    if debt_ratio is not None and not pd.isna(debt_ratio) and debt_ratio > s["debt_ratio_safe"]:
        debt_ok = False
    if (interest_cov is not None and not pd.isna(interest_cov)
            and interest_cov < s["interest_coverage_safe"] and interest_cov > 0):
        debt_ok = False
    result["debt_safety"] = {"score": 1.0 if debt_ok else 0,
                             "label": "安全" if debt_ok else "有压力",
                             "value": {"debt_ratio": round(debt_ratio, 1) if debt_ratio else None,
                                       "interest_cov": round(interest_cov, 1) if interest_cov else None}}

    result["total"] = round(min(
        sum(v.get("score", 0) for k, v in result.items() if k != "total"
    ), max_score), 1)
    return result


# ============================================================
# L4: 行业校准 (0-10)
# ============================================================

# 行业内相对排名权重
L4_METRIC_WEIGHTS = {
    "gross_margin": 0.25,     # 毛利率行业内越高越好
    "revenue_yoy": 0.20,      # 营收增速相对排名
    "net_margin": 0.20,       # 净利率相对排名
    "roic": 0.20,             # ROIC相对排名
    "debt_ratio": 0.15,       # 有息负债率越低越好(反向)
}


def _score_l4(code: str, t_date: str, industry_l3: str) -> dict:
    """行业校准：同行业相对排名 + 行业特征加成 (0-10)。

    核心逻辑：成长股的各项指标在行业内横向比较，
    而非绝对阈值——好行业里的中等公司可能优于差行业里的第一名。
    """
    result = {"total": 5.0}  # 基准分
    snap = get_financial_snapshot(t_date)

    # 筛选同行业股票
    from growth_os.data import load_industry_map
    ind_map = load_industry_map()
    peers = [c for c in snap["code"].unique()
             if ind_map.get(c) == industry_l3]
    peer_snap = snap[snap["code"].isin(peers)]

    if len(peer_snap) < 3:
        result["note"] = {"label": f"同业样本不足({len(peer_snap)}只)，使用通用校准"}
        return _l4_fallback(industry_l3, result)

    result["industry_peers"] = {"label": f"同业{len(peer_snap)}只"}

    # 获取个股票数据
    stock_row = snap[snap["code"] == code]
    if stock_row.empty:
        return _l4_fallback(industry_l3, result)
    stock = stock_row.iloc[0]

    # --- 行业内百分位计算 ---
    percentiles = {}
    details = {}

    # 1. 毛利率 (正向)
    gm = stock.get("gross_margin")
    if gm is not None and not pd.isna(gm):
        gm_peers = peer_snap["gross_margin"].dropna()
        if len(gm_peers) >= 3:
            pct = (gm_peers < gm).sum() / len(gm_peers) * 100
            percentiles["gross_margin"] = pct
            details["gross_margin"] = {
                "value": round(gm, 1),
                "percentile": round(pct, 1),
                "label": f"毛利率{gm:.1f}%(行业分位{pct:.0f}%)",
            }

    # 2. 营收增速 (正向)
    rev_yoy = stock.get("revenue_yoy")
    if rev_yoy is not None and not pd.isna(rev_yoy):
        rev_peers = peer_snap["revenue_yoy"].dropna()
        if len(rev_peers) >= 3:
            pct = (rev_peers < rev_yoy).sum() / len(rev_peers) * 100
            percentiles["revenue_yoy"] = pct
            details["revenue_yoy"] = {
                "value": round(rev_yoy, 1),
                "percentile": round(pct, 1),
                "label": f"营收增速{rev_yoy:.1f}%(行业分位{pct:.0f}%)",
            }

    # 3. 净利率 (正向)
    nm = stock.get("net_margin")
    if nm is not None and not pd.isna(nm):
        nm_peers = peer_snap["net_margin"].dropna()
        if len(nm_peers) >= 3:
            pct = (nm_peers < nm).sum() / len(nm_peers) * 100
            percentiles["net_margin"] = pct
            details["net_margin"] = {
                "value": round(nm, 1),
                "percentile": round(pct, 1),
                "label": f"净利率{nm:.1f}%(行业分位{pct:.0f}%)",
            }

    # 4. ROIC (正向)
    roic_val = stock.get("roic")
    if roic_val is not None and not pd.isna(roic_val):
        roic_peers = peer_snap["roic"].dropna()
        if len(roic_peers) >= 3:
            pct = (roic_peers < roic_val).sum() / len(roic_peers) * 100
            percentiles["roic"] = pct
            details["roic"] = {
                "value": round(roic_val, 1),
                "percentile": round(pct, 1),
                "label": f"ROIC{roic_val:.1f}%(行业分位{pct:.0f}%)",
            }

    # 5. 有息负债率 (反向：越低越好)
    debt = stock.get("interest_bearing_debt_ratio")
    if debt is not None and not pd.isna(debt):
        debt_peers = peer_snap["interest_bearing_debt_ratio"].dropna()
        if len(debt_peers) >= 3:
            # 反向：负债率低=分位高
            pct = (debt_peers > debt).sum() / len(debt_peers) * 100
            percentiles["debt_ratio"] = pct
            details["debt_ratio"] = {
                "value": round(debt, 1),
                "percentile": round(pct, 1),
                "label": f"有息负债率{debt:.1f}%(优于{pct:.0f}%同业)",
            }

    # --- 加权综合百分位 → 0-10 映射 ---
    if percentiles:
        weighted_pct = sum(
            percentiles.get(k, 50) * L4_METRIC_WEIGHTS[k]
            for k in L4_METRIC_WEIGHTS
        ) / sum(L4_METRIC_WEIGHTS[k] for k in L4_METRIC_WEIGHTS
                 if k in percentiles or True)

        # 调整权重和：只计算有数据的指标
        available_weight = sum(
            w for k, w in L4_METRIC_WEIGHTS.items() if k in percentiles)
        if available_weight > 0:
            weighted_pct = sum(
                percentiles[k] * L4_METRIC_WEIGHTS[k]
                for k in percentiles
            ) / available_weight

        # 百分位 → 分数映射: 0-100 → 0-10 (线性)
        industry_score = round(weighted_pct / 10, 1)

        # 绝对底线约束：ROIC<WACC时行业分位打折（"行业都烂≠你好"）
        roic_abs = stock.get("roic")
        wacc_pct = 9.0  # 默认WACC=9%（ROIC字段为百分比值，如3.07=3.07%）
        if roic_abs is not None and not pd.isna(roic_abs) and roic_abs < wacc_pct:
            cap_factor = 0.7
            industry_score = round(industry_score * cap_factor, 1)
            weighted_pct = round(weighted_pct * cap_factor, 1)

        result["total"] = industry_score
        result["weighted_percentile"] = {
            "value": round(weighted_pct, 1),
            "label": f"行业加权分位{weighted_pct:.0f}% → 基础分{industry_score:.1f}",
        }
        if roic_abs is not None and not pd.isna(roic_abs) and roic_abs < wacc_pct:
            result["weighted_percentile"]["label"] += "（ROIC<WACC，行业优势折扣×0.7）"

        # 同业排名估算
        peer_count = len(peer_snap)
        rank_approx = max(1, peer_count - int(round(weighted_pct / 100 * peer_count)))
        result["peer_rank"] = {
            "value": rank_approx,
            "total": peer_count,
            "label": f"赛道排名第{rank_approx}/{peer_count}",
        }
    else:
        result["total"] = 5.0

    # --- 行业特征加成 ---
    adj = INDUSTRY_ADJUSTMENTS.get(industry_l3, {})
    bonus = 0.0
    bonus_notes = []

    # 主动备产型行业：存货扩张容忍度高
    if adj.get("inventory_growth_threshold", 1.5) > 1.5:
        bonus += 0.5
        bonus_notes.append("主动备产型+0.5")

    # 订单先行型行业：预收款/合同负债权重高
    if adj.get("advance_receipts_weight", 1.0) > 1.2:
        bonus += 0.5
        bonus_notes.append("订单先行型+0.5")

    # 研发驱动型行业
    if adj.get("rd_intensity_high", 8) > 10:
        bonus += 0.5
        bonus_notes.append("研发驱动型+0.5")

    # 利润容忍型行业（创新药/器械）：不因低利润惩罚
    if adj.get("profit_tolerance"):
        if "net_margin" in percentiles and percentiles["net_margin"] < 30:
            # 低利润在创新药行业正常，补回一些分数
            bonus += 1.0
            bonus_notes.append("创新行业利润容忍+1.0")

    # 毛利率敏感型行业：毛利率权重加倍
    if adj.get("gross_margin_sensitive"):
        if "gross_margin" in percentiles and percentiles["gross_margin"] > 50:
            bonus += 0.5
            bonus_notes.append("毛利率优势行业+0.5")

    if bonus_notes:
        result["industry_bonus"] = {
            "value": round(bonus, 1),
            "label": ", ".join(bonus_notes),
        }

    result["total"] = round(min(result["total"] + bonus, 10.0), 1)

    # 汇总详情
    for k, v in details.items():
        result[k] = v

    if adj:
        adj_notes = [f"{k}={v}" for k, v in adj.items()
                     if k in ("inventory_growth_threshold", "advance_receipts_weight",
                              "rd_intensity_high")]
        if adj_notes:
            result["industry_config"] = {"label": ", ".join(adj_notes)}

    return result


def _l4_fallback(industry_l3: str, result: dict) -> dict:
    """当同行业样本不足时的回退逻辑。"""
    adj = INDUSTRY_ADJUSTMENTS.get(industry_l3, {})
    if adj:
        result["industry_match"] = {"label": f"行业特征匹配: {industry_l3}"}
        result["total"] = 6.0  # 有行业配置但无法做相对排名
    else:
        result["total"] = 5.0
    return result


# ============================================================
# L5: 预期差 (0-10)
# ============================================================

def compute_forward_growth(code: str, t_date: str) -> tuple[float | None, str]:
    """计算前瞻增速代理变量 g_proxy。

    指数加权近4季营收yoy（权重 0.4/0.3/0.2/0.1），
    合同负债交叉验证，OCF含金量折扣。

    Returns:
        (g, source_tag) — g 为小数如 0.30=30%，source_tag 标识来源
    """
    rev_yoy_series = get_quarterly_series(
        code, "revenue_yoy", n_quarters=8, t_date=t_date
    ).dropna()

    if len(rev_yoy_series) < 3:
        # 回退到3年CAGR
        cagr = compute_revenue_cagr_3y(code, t_date)
        if cagr is not None:
            return max(cagr / 100, 0.05), "fallback_cagr3y"
        return None, "insufficient_data"

    # 指数加权：近4季 yoy，越近权重越高
    recent = rev_yoy_series.iloc[-4:].values if len(rev_yoy_series) >= 4 else rev_yoy_series.values
    n = len(recent)
    alpha = 0.55
    weights = [alpha ** (n - 1 - i) for i in range(n)]
    weights_sum = sum(weights)
    g_ewa = sum(v * w for v, w in zip(recent, weights)) / weights_sum

    if g_ewa <= 0:
        return 0.05, "ewa_floor"

    # 合同负债交叉验证：合同负债是收入先行指标
    cl_series = get_quarterly_series(
        code, "contract_liabilities", n_quarters=8, t_date=t_date
    ).dropna()
    if len(cl_series) >= 3:
        cl_recent = cl_series.iloc[-4:].mean() if len(cl_series) >= 4 else cl_series.mean()
        cl_old = cl_series.iloc[-8:-4].mean() if len(cl_series) >= 8 else cl_series.iloc[:4].mean()
        if cl_old > 0:
            cl_growth = (cl_recent / cl_old - 1)
            if cl_growth > 0:
                g_ewa = max(g_ewa, cl_growth * 0.8)  # 合同负债增速衰减后作为下限
                return min(g_ewa, 0.80), "ewa_cl_crossvalidated"

    # OCF含金量折扣
    ocf_series = get_quarterly_series(
        code, "operating_cash_flow", n_quarters=12, t_date=t_date
    ).dropna()
    profit_series = get_quarterly_series(
        code, "deducted_profit_q", n_quarters=12, t_date=t_date
    ).dropna()
    if len(ocf_series) >= 4 and len(profit_series) >= 4:
        common = ocf_series.index.intersection(profit_series.index)
        if len(common) >= 4:
            ocf_sum = ocf_series.loc[common].sum()
            profit_sum = abs(profit_series.loc[common].sum())
            if profit_sum > 0:
                ocf_ratio = ocf_sum / profit_sum
                if ocf_ratio < 0.75:
                    g_ewa *= 0.7
                    return max(g_ewa, 0.04), "ewa_ocf_discounted"
                elif ocf_ratio < 0.95:
                    g_ewa *= 0.9

    # 前瞻修正：近2季YoY连续环比回落 → 历史外推高估成长性
    if len(rev_yoy_series) >= 4:
        recent_mean = rev_yoy_series.iloc[-2:].mean()
        older_mean = rev_yoy_series.iloc[-4:-2].mean()
        if older_mean > 0 and recent_mean < older_mean * 0.95:
            ratio = recent_mean / older_mean
            g_ewa *= max(ratio, 0.6)
            g_ewa = max(0.04, min(g_ewa, 0.80))
            return g_ewa, "ewa_yoy_declining"

    g_ewa = max(0.04, min(g_ewa, 0.80))
    return g_ewa, "ewa_yoy"


def _score_l5(code: str, t_date: str, industry_l3: str) -> dict:
    s = L5_SCORING
    max_score = s["l5_max_score"]
    result = {"total": 0.0}

    snap = get_financial_snapshot(t_date)
    row = snap[snap["code"] == code]
    if row.empty:
        return result
    row = row.iloc[0]

    pe = get_pe_ttm(code, t_date)

    # 1. PEG (0-4) — 用前瞻增速代理 g_proxy
    g_proxy, g_source = compute_forward_growth(code, t_date)

    # v2.5: 成熟期PEG适用性折扣（PEG框架部分适用→PEG子项×0.5）
    from growth_os.config import PEG_CONFIDENCE, PEG_CONFIDENCE_DEFAULT
    peg_conf = PEG_CONFIDENCE.get(industry_l3, PEG_CONFIDENCE_DEFAULT)
    peg_maturity_discount = 1.0
    if peg_conf.get("level") == "caution":
        peg_maturity_discount = 0.7
    elif peg_conf.get("level") == "misleading":
        peg_maturity_discount = 0.3

    # g* 可信度检验：当 g* 与最新营收增速严重背离时，标记不可信
    g_trusted = True
    g_trust_note = ""
    rev_yoy_latest = row.get("revenue_yoy") if not row.empty else None
    if g_proxy is not None and rev_yoy_latest is not None and not pd.isna(rev_yoy_latest):
        g_pct = g_proxy * 100
        # 只在 g* 明显高估时标记不可信（g*远高于实际=过度乐观）
        sign_conflict = (g_pct > 10 and rev_yoy_latest < -5)       # g*正增长但实际营收负增长
        over_optimistic = (g_pct - rev_yoy_latest) > 30             # g*比实际增速高30pp以上
        if sign_conflict or over_optimistic:
            g_trusted = False
            g_trust_note = f"（⚠️ g*={g_pct:.0f}%与近期增速{rev_yoy_latest:.0f}%背离，可信度低）"

    if pe is not None and g_proxy is not None and g_proxy > 0:
        peg = pe / (g_proxy * 100)  # g_proxy 是小数(0.30=30%)
        result["peg_ratio"] = {
            "value": round(peg, 2),
            "g_proxy": round(g_proxy * 100, 1),
            "g_source": g_source,
            "g_trusted": g_trusted,
        }
        # g* 不可信时用条件语态替代确定性标签（"低估/合理/高估"不可直接采信）
        if not g_trusted:
            result["peg_ratio"]["score"] = 1.0
            result["peg_ratio"]["label"] = (
                f"⚠️ PEG={peg:.1f} (g*={g_proxy*100:.0f}%与近期增速{rev_yoy_latest:.0f}%背离→可信度低，不可直接采信)"
            )
        elif peg < s["peg_undervalued"]:
            result["peg_ratio"]["score"] = 4.0
            result["peg_ratio"]["label"] = f"低估(PEG={peg:.1f}, g={g_proxy*100:.0f}%)"
        elif peg < s["peg_fair"]:
            result["peg_ratio"]["score"] = 2.5
            result["peg_ratio"]["label"] = f"合理(PEG={peg:.1f}, g={g_proxy*100:.0f}%)"
        elif peg < s["peg_overvalued"]:
            result["peg_ratio"]["score"] = 1.0
            result["peg_ratio"]["label"] = f"偏贵(PEG={peg:.1f}, g={g_proxy*100:.0f}%)"
        else:
            result["peg_ratio"]["score"] = 0
            result["peg_ratio"]["label"] = f"高估(PEG={peg:.1f}, g={g_proxy*100:.0f}%)"
    else:
        result["peg_ratio"] = {"score": 0, "label": "数据不足", "g_proxy": None, "g_source": g_source if g_proxy else "insufficient_data", "g_trusted": False}

    # v2.5: PEG适用域折扣（misleading→×0.3, caution→×0.7）
    if peg_maturity_discount < 1.0 and isinstance(result["peg_ratio"].get("score"), (int, float)):
        old = result["peg_ratio"]["score"]
        if old > 0:
            result["peg_ratio"]["score"] = round(old * peg_maturity_discount, 1)
            result["peg_ratio"]["label"] += f"（{peg_conf['level']}行业→PEG×{peg_maturity_discount}）"

    # 2. PE 行业内分位 (0-3)
    if pe is not None:
        all_codes = snap["code"].unique()
        # 同行业PE对比
        same_industry = snap[snap.apply(
            lambda r: get_industry(r["code"]) == industry_l3, axis=1
        )]
        if len(same_industry) > 3:
            pe_values = []
            for c in same_industry["code"]:
                pe_c = get_pe_ttm(c, t_date)
                if pe_c is not None and pe_c > 0:
                    pe_values.append(pe_c)
            if pe_values:
                percentile = (sum(1 for p in pe_values if p < pe) / len(pe_values)) * 100
                result["pe_percentile"] = {"value": round(percentile, 1)}
                if percentile < s["pe_percentile_low"]:
                    result["pe_percentile"]["score"] = 3.0
                    result["pe_percentile"]["label"] = f"行业内偏低(分位{percentile:.0f}%)"
                elif percentile < s["pe_percentile_high"]:
                    result["pe_percentile"]["score"] = 1.5
                    result["pe_percentile"]["label"] = f"行业内中等(分位{percentile:.0f}%)"
                else:
                    result["pe_percentile"]["score"] = 0
                    result["pe_percentile"]["label"] = f"行业内偏高(分位{percentile:.0f}%)"
            else:
                result["pe_percentile"] = {"score": 0, "label": "行业内无可比数据"}
        else:
            result["pe_percentile"] = {"score": 0, "label": "行业内股票数不足"}
    else:
        result["pe_percentile"] = {"score": 0, "label": "无PE数据"}

    # 2.5 PE 自身历史分位 (0-2) — v2.1.3
    if pe is not None:
        price_df = get_price_data(code)
        if price_df is not None and "peTTM" in price_df.columns:
            pe_hist = price_df[price_df["date"] <= pd.Timestamp(t_date)].tail(1260)  # ~5年
            pe_vals = pe_hist["peTTM"].dropna()
            pe_vals = pe_vals[(pe_vals > 0) & (pe_vals < 500)]  # 剔除极端值
            if len(pe_vals) >= 250:  # 至少1年数据
                hist_pct = (pe_vals < pe).sum() / len(pe_vals) * 100
                result["pe_hist_pct"] = {"value": round(hist_pct, 1)}
                if hist_pct < 30:
                    result["pe_hist_pct"]["score"] = 2.0
                    result["pe_hist_pct"]["label"] = f"自身历史低位(分位{hist_pct:.0f}%)"
                elif hist_pct < 70:
                    result["pe_hist_pct"]["score"] = 1.0
                    result["pe_hist_pct"]["label"] = f"自身历史中位(分位{hist_pct:.0f}%)"
                else:
                    result["pe_hist_pct"]["score"] = 0
                    result["pe_hist_pct"]["label"] = f"自身历史高位(分位{hist_pct:.0f}%)"
            else:
                result["pe_hist_pct"] = {"score": 0, "label": "历史数据不足"}
        else:
            result["pe_hist_pct"] = {"score": 0, "label": "无历史PE数据"}
    else:
        result["pe_hist_pct"] = {"score": 0, "label": "无PE数据"}

    # 3. 增长加速度 (0-3)
    rev_yoy_series = get_quarterly_series(
        code, "revenue_yoy", n_quarters=6, t_date=t_date
    ).dropna()
    if len(rev_yoy_series) >= 4:
        recent = rev_yoy_series.iloc[-2:].mean()
        older = rev_yoy_series.iloc[-4:-2].mean()
        if recent > older * 1.1:
            result["growth_acceleration"] = {"score": 3.0,
                                             "label": f"加速({older:.1f}%→{recent:.1f}%)"}
        elif recent >= older * 0.9:
            result["growth_acceleration"] = {"score": 1.5,
                                             "label": f"平稳({older:.1f}%→{recent:.1f}%)"}
        else:
            result["growth_acceleration"] = {"score": 0,
                                             "label": f"减速({older:.1f}%→{recent:.1f}%)"}
    else:
        result["growth_acceleration"] = {"score": 0, "label": "数据不足"}

    # 增长质量折扣：周期价格型行业的 PEG/growth_accel 得分打折
    from growth_os.config import PEG_CONFIDENCE, PEG_CONFIDENCE_DEFAULT
    peg_conf = PEG_CONFIDENCE.get(industry_l3, PEG_CONFIDENCE_DEFAULT)
    if peg_conf["level"] == "misleading":
        if "peg_ratio" in result and result["peg_ratio"].get("score", 0) > 0:
            result["peg_ratio"]["score"] = round(result["peg_ratio"]["score"] * 0.3, 1)
            result["peg_ratio"]["label"] += " (周期型折扣×0.3)"
        if "growth_acceleration" in result:
            result["growth_acceleration"]["score"] = round(result["growth_acceleration"]["score"] * 0.5, 1)
            result["growth_acceleration"]["label"] += " (周期型折扣×0.5)"
    elif peg_conf["level"] == "caution":
        if "peg_ratio" in result and result["peg_ratio"].get("score", 0) > 0:
            result["peg_ratio"]["score"] = round(result["peg_ratio"]["score"] * 0.7, 1)
            result["peg_ratio"]["label"] += " (谨慎折扣×0.7)"

    result["total"] = round(min(
        sum(v.get("score", 0) for k, v in result.items() if k != "total"
    ), max_score), 1)
    return result


def score_cycle_position(code: str, t_date: str) -> dict:
    """周期位置评估 — 用于 is_growth_eligible=False 的标的。

    四维评估（不参与成长股综合分）：
    1. 现金流安全性: FCF/营收
    2. 订单能见度: 合同负债/营收
    3. 债务安全性: 有息负债率
    4. 库存位置: 存货周转天数
    """
    snap = get_financial_snapshot(t_date)
    row = snap[snap["code"] == code]
    if row.empty:
        return {"dimensions": [], "total_note": "数据不足"}
    row = row.iloc[0]

    dims = []
    revenue = row.get("revenue") or 1

    fcff = row.get("fcff_per_share")
    shares = row.get("total_shares")
    if fcff is not None and shares is not None and not pd.isna(fcff):
        fcf_total = fcff * shares
        fcf_yield = fcf_total / revenue * 100 if revenue > 0 else 0
        if fcf_yield > 5:
            dims.append(f"🟢 FCF充裕(FCF/营收={fcf_yield:.1f}%)")
        elif fcf_yield > 0:
            dims.append(f"🟡 FCF为正(FCF/营收={fcf_yield:.1f}%)")
        else:
            dims.append(f"🔴 FCF为负，现金消耗中")

    cl = row.get("contract_liabilities")
    if cl is not None and not pd.isna(cl) and cl > 0:
        cl_ratio = cl / revenue * 100
        if cl_ratio > 20:
            dims.append(f"🟢 订单充盈(合同负债/营收={cl_ratio:.0f}%)")
        elif cl_ratio > 5:
            dims.append(f"🟡 有在手订单(合同负债/营收={cl_ratio:.0f}%)")
        else:
            dims.append(f"🟡 订单偏薄(合同负债/营收={cl_ratio:.0f}%)")

    debt_ratio = row.get("interest_bearing_debt_ratio")
    if debt_ratio is not None and not pd.isna(debt_ratio):
        if debt_ratio < 30:
            dims.append(f"🟢 低杠杆(有息负债率={debt_ratio:.1f}%)")
        elif debt_ratio < 50:
            dims.append(f"🟡 中等杠杆(有息负债率={debt_ratio:.1f}%)")
        else:
            dims.append(f"🔴 高杠杆(有息负债率={debt_ratio:.1f}%)")

    inv_days = row.get("inventory_days")
    if inv_days is not None and not pd.isna(inv_days):
        if inv_days < 90:
            dims.append(f"🟢 库存轻(周转{inv_days:.0f}天)")
        elif inv_days < 180:
            dims.append(f"🟡 库存适中(周转{inv_days:.0f}天)")
        else:
            dims.append(f"🔴 库存积压(周转{inv_days:.0f}天；制造业健康区≈120-170天)→出清未完成")

    greens = sum(1 for d in dims if "🟢" in d)
    reds = sum(1 for d in dims if "🔴" in d)
    has_inventory_risk = any("库存积压" in d for d in dims)
    if greens >= 3 and reds == 0:
        total_note = "周期安全性较高，可关注拐点信号（营收转正/ROIC回升）"
    elif reds >= 2:
        total_note = "周期位置偏弱，需等待更多出清信号（库存下降/资产负债改善）"
    elif has_inventory_risk:
        total_note = "周期位置承压：现金流与订单支撑短期生存，但库存积压预示跌价准备风险，需关注减值损失计提"
    else:
        total_note = "周期位置中性，部分维度改善中，建议持续跟踪"

    # 订单转化效率：合同负债高但营收负增长 → 转化存疑
    rev_yoy = row.get("revenue_yoy")
    if rev_yoy is not None and not pd.isna(rev_yoy) and rev_yoy < -5 and cl is not None and cl > 0:
        cl_ratio = cl / revenue * 100
        if cl_ratio > 20:
            dims.append(f"⚠️ 合同负债/营收={cl_ratio:.0f}%但营收{rev_yoy:.0f}%，需确认订单转化效率（交付延迟/订单延期/长周期订单结构）")

    return {"dimensions": dims, "total_note": total_note}
