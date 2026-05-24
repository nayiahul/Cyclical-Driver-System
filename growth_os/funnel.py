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
    compute_revenue_cagr_3y,
)
from growth_os.wacc import compute_wacc


def run_funnel(
    code: str, t_date: str, industry_l3: str = None,
    lifecycle: LifecycleStage = None
) -> dict:
    """对单只股票执行五层漏斗检查。

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

    # ---- L1: 排雷 ----
    l1 = _check_l1(code, t_date, industry_l3)
    result["l1_details"] = l1
    result["l1_red_flags"] = [k for k, v in l1.items() if v.get("red", False)]
    result["pass_l1"] = len(result["l1_red_flags"]) < L1_THRESHOLDS["max_red_flags"]

    if not result["pass_l1"]:
        return result

    # ---- L2: 护城河 ----
    l2 = _score_l2(code, t_date, industry_l3)
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

    # 1. 营收3年CAGR — 用绝对营收TTM算3年CAGR
    rev_yoy = row.get("revenue_yoy")
    rev_yoy_val = rev_yoy if rev_yoy is not None and not pd.isna(rev_yoy) else 0
    cagr_3y = compute_revenue_cagr_3y(code, t_date)
    result["revenue_cagr_3y"] = {
        "value": round(cagr_3y, 1) if cagr_3y else None,
        "red": cagr_3y is not None and cagr_3y < t["revenue_cagr_3y_min"],
        "detail": f"营收3年CAGR={cagr_3y:.1f}%" if cagr_3y else "无足够数据",
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
        "red": ocf_profit_ratio is not None and ocf_profit_ratio < t["ocf_profit_ratio_3y_min"],
        "detail": f"OCF/净利润(3年)={ocf_profit_ratio:.2f}" if ocf_profit_ratio else "数据不足",
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
            recv_surge = (rev_yoy_val > 0 and recv_growth > rev_yoy_val / 100 * t["receivable_surge_ratio"])
            result["receivable_surge"] = {
                "value": round(recv_growth * 100, 1),
                "red": recv_surge,
                "detail": f"应收增速{recv_growth*100:.1f}% vs 营收增速{rev_yoy_val:.1f}%",
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

    return result


# ============================================================
# L2: 护城河 (0-10)
# ============================================================

def _score_l2(code: str, t_date: str, industry_l3: str) -> dict:
    s = L2_SCORING
    result = {"total": 0.0}
    max_score = s["l2_max_score"]
    snap = get_financial_snapshot(t_date)
    row = snap[snap["code"] == code]
    if row.empty:
        return result
    row = row.iloc[0]

    # 1. 毛利率趋势 (0-3)
    gm_series = get_quarterly_series(
        code, "gross_margin", n_quarters=12, t_date=t_date
    ).dropna()
    if len(gm_series) >= 8:
        recent_gm = gm_series.iloc[-4:].mean()
        old_gm = gm_series.iloc[-8:-4].mean()
        if recent_gm > old_gm * 1.02:
            result["gross_margin_trend"] = {"score": s["gross_margin_up_weight"],
                                            "label": "上升", "recent": round(recent_gm, 1)}
        elif recent_gm >= old_gm * 0.98:
            result["gross_margin_trend"] = {"score": s["gross_margin_stable_weight"],
                                            "label": "稳定", "recent": round(recent_gm, 1)}
        else:
            result["gross_margin_trend"] = {"score": 0, "label": "下降",
                                            "recent": round(recent_gm, 1)}
    else:
        result["gross_margin_trend"] = {"score": 0, "label": "数据不足"}

    # 2. 费用率杠杆 (0-2)
    # (销售+管理)费用率随规模摊薄
    selling_series = get_quarterly_series(code, "selling_expense", n_quarters=8, t_date=t_date)
    admin_series = get_quarterly_series(code, "admin_expense", n_quarters=8, t_date=t_date)
    revenue_q_series = get_quarterly_series(code, "revenue_q", n_quarters=8, t_date=t_date)

    if (len(selling_series.dropna()) >= 4 and len(admin_series.dropna()) >= 4
            and len(revenue_q_series.dropna()) >= 4):
        # 最近4季 vs 前4季
        recent_rev = revenue_q_series.iloc[-4:].sum()
        old_rev = revenue_q_series.iloc[-8:-4].sum()
        if old_rev > 0:
            recent_expense_ratio = (selling_series.iloc[-4:].sum() +
                                    admin_series.iloc[-4:].sum()) / recent_rev * 100
            old_expense_ratio = (selling_series.iloc[-8:-4].sum() +
                                 admin_series.iloc[-8:-4].sum()) / old_rev * 100
            if recent_expense_ratio < old_expense_ratio * 0.95:
                result["expense_leverage"] = {"score": s["expense_leverage_weight"],
                                              "label": "释放中",
                                              "recent": round(recent_expense_ratio, 1)}
            elif recent_expense_ratio <= old_expense_ratio * 1.05:
                result["expense_leverage"] = {"score": s["expense_leverage_weight"] / 2,
                                              "label": "刚性",
                                              "recent": round(recent_expense_ratio, 1)}
            else:
                result["expense_leverage"] = {"score": 0, "label": "恶化",
                                              "recent": round(recent_expense_ratio, 1)}
        else:
            result["expense_leverage"] = {"score": 0, "label": "数据不足"}
    else:
        result["expense_leverage"] = {"score": 0, "label": "数据不足"}

    # 3. 研发强度 (0-2)
    rd = row.get("rd_expense", 0) or 0
    revenue = row.get("revenue", 0) or 0
    if revenue > 0:
        rd_ratio = rd / revenue * 100
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

    # 4. 合同负债领先 (0-2)
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
            # 行业校准: 白酒/军工合同负债权重更高
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
                result["contract_liabilities"] = {
                    "score": adj_contract_weight / 2,
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

    # 合计
    result["total"] = round(min(
        sum(v["score"] for k, v in result.items() if k != "total"
    ), max_score), 1)
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

    # 1. ROIC vs WACC (0-4)
    roic = row.get("roic")
    wacc = compute_wacc(code, t_date)
    if roic is not None and not pd.isna(roic):
        if wacc is not None:
            spread = roic - wacc
            result["roic_vs_wacc"] = {
                "value": {"roic": round(roic, 1), "wacc": round(wacc, 1),
                          "spread": round(spread, 1)},
                "label": f"ROIC({roic:.1f}%) vs WACC({wacc:.1f}%)",
            }
            if spread > s["roic_wacc_spread_excellent"]:
                result["roic_vs_wacc"]["score"] = 4.0
                result["roic_vs_wacc"]["label"] += " >> 优秀"
            elif spread > 0:
                result["roic_vs_wacc"]["score"] = 2.5
                result["roic_vs_wacc"]["label"] += " > 及格"
            else:
                result["roic_vs_wacc"]["score"] = 0
                result["roic_vs_wacc"]["label"] += " < 毁灭价值"
        else:
            # WACC 不可用，回退到绝对阈值：ROIC > 10% 优秀, > 5% 及格
            result["roic_vs_wacc"] = {
                "value": {"roic": round(roic, 1), "wacc": None, "spread": None},
                "label": f"ROIC={roic:.1f}% (WACC不可算)",
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
                    "label": f"ROIC提升({prior_fy:.1f}%→{current_fy:.1f}%)"}
            elif current_fy >= prior_fy * 0.9:
                result["roic_trend"] = {"score": 1.0,
                    "label": f"ROIC平稳({prior_fy:.1f}%→{current_fy:.1f}%)"}
            else:
                result["roic_trend"] = {"score": 0,
                    "label": f"ROIC下滑({prior_fy:.1f}%→{current_fy:.1f}%)"}
        else:
            # 无足够FY数据，回退到连续4季对比
            recent = roic_series.iloc[-4:].mean()
            old = roic_series.iloc[-8:-4].mean()
            if recent > old:
                result["roic_trend"] = {"score": 2.0,
                    "label": f"ROIC提升({old:.1f}→{recent:.1f})"}
            elif recent >= old * 0.9:
                result["roic_trend"] = {"score": 1.0, "label": "ROIC平稳"}
            else:
                result["roic_trend"] = {"score": 0,
                    "label": f"ROIC下滑({old:.1f}→{recent:.1f})"}
    else:
        result["roic_trend"] = {"score": 0, "label": "数据不足"}

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

def _score_l4(code: str, t_date: str, industry_l3: str) -> dict:
    """行业翻译器：根据行业特征调整解读。一期返回基础行业匹配分。"""
    result = {"total": 7.0}  # 默认基础分
    adj = INDUSTRY_ADJUSTMENTS.get(industry_l3, {})

    if not adj:
        result["note"] = {"label": f"通用校准({industry_l3})"}
        return result

    # 行业匹配度
    result["industry_match"] = {"label": f"行业校准: {industry_l3}"}
    notes = []
    for k, v in adj.items():
        notes.append(f"{k}={v}")

    # 存货阈值已放宽 → 加分
    if adj.get("inventory_growth_threshold", 1.5) > 1.5:
        result["total"] += 1.0
        result["inv_tolerance"] = {"label": "存货扩张容忍度高(主动备产型行业)"}

    # 预收款权重高 → 行业重视订单先行
    if adj.get("advance_receipts_weight", 1.0) > 1.2:
        result["total"] += 0.5
        result["order_leading"] = {"label": "订单先行型行业"}

    # 高研发行业
    if adj.get("rd_intensity_high", 8) > 10:
        result["total"] += 0.5
        result["rd_heavy"] = {"label": "研发驱动型行业"}

    result["adjustments"] = {"label": ", ".join(notes)}
    result["total"] = min(result["total"], 10.0)
    return result


# ============================================================
# L5: 预期差 (0-10)
# ============================================================

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

    # 1. PEG (0-4)
    rev_yoy = row.get("revenue_yoy")
    if pe is not None and rev_yoy is not None and not pd.isna(rev_yoy) and rev_yoy > 0:
        peg = pe / rev_yoy
        result["peg_ratio"] = {"value": round(peg, 2)}
        if peg < s["peg_undervalued"]:
            result["peg_ratio"]["score"] = 4.0
            result["peg_ratio"]["label"] = f"低估(PEG={peg:.1f})"
        elif peg < s["peg_fair"]:
            result["peg_ratio"]["score"] = 2.5
            result["peg_ratio"]["label"] = f"合理(PEG={peg:.1f})"
        elif peg < s["peg_overvalued"]:
            result["peg_ratio"]["score"] = 1.0
            result["peg_ratio"]["label"] = f"偏贵(PEG={peg:.1f})"
        else:
            result["peg_ratio"]["score"] = 0
            result["peg_ratio"]["label"] = f"高估(PEG={peg:.1f})"
    else:
        result["peg_ratio"] = {"score": 0, "label": "数据不足"}

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

    result["total"] = round(min(
        sum(v.get("score", 0) for k, v in result.items() if k != "total"
    ), max_score), 1)
    return result
