"""打分卡 — GrowthScorecard 数据结构与综合评分计算。"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import numpy as np

from growth_os.regime_router import (
    StockRegime, classify_regime, regime_decision, REGIME_ROUTES,
)

from growth_os.config import LifecycleStage
from growth_os.lifecycle import get_weights, resolve_weights


class L5Status(Enum):
    OK = "ok"             # PE/PEG 完整可用
    PARTIAL = "partial"   # 仅增长加速度可用，PE/PEG 缺失
    MISSING = "missing"   # 全部不可用


@dataclass
class GrowthScorecard:
    """成长股体检打分卡。"""
    code: str
    name: str = ""
    industry_l3: str = ""
    industry_l1: str = ""
    lifecycle: LifecycleStage = LifecycleStage.DECLINE
    lifecycle_reason: str = ""

    # A区: 增长真实性
    pass_l1: bool = True
    l1_verdict: str = ""
    l1_absolute_reds: list = field(default_factory=list)
    l1_conditional_reds: list = field(default_factory=list)
    l1_red_flags: list = field(default_factory=list)
    revenue_cagr_3y: Optional[float] = None
    deducted_yoy: Optional[float] = None
    revenue_yoy: Optional[float] = None
    ocf_profit_ratio_3y: Optional[float] = None
    goodwill_ratio: Optional[float] = None

    # B区: 增长质量
    score_l2: float = np.nan
    gross_margin_trend: str = ""
    expense_leverage: str = ""
    contract_liab_growth: Optional[float] = None
    rd_ratio: Optional[float] = None

    # C区: 资本效率
    score_l3: float = np.nan
    roic: Optional[float] = None
    roic_ttm: Optional[float] = None
    wacc: Optional[float] = None
    roic_minus_wacc: Optional[float] = None
    roe: Optional[float] = None
    fcf_per_share: Optional[float] = None
    debt_ratio: Optional[float] = None

    # D区: 行业校准
    score_l4: float = np.nan
    industry_weighted_pct: Optional[float] = None

    # E区: 预期差
    score_l5: float = np.nan
    peg: Optional[float] = None
    pe_percentile: Optional[float] = None
    growth_accel: str = ""

    # 综合
    composite_score: float = np.nan
    quality_score: float = np.nan  # L1-L4 成长质量分（不含L5）
    l5_status: str = ""           # L5Status: ok/partial/missing
    decision: str = ""
    stock_regime: str = ""         # StockRegime value
    capex_phase: str = ""          # CAPEX cycle phase
    persistence_score: float = np.nan  # 增长持续性概率 0-100
    is_growth_eligible: bool = True
    block_reason: str = ""
    _saved_weights: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "industry_l3": self.industry_l3,
            "industry_l1": self.industry_l1,
            "lifecycle": self.lifecycle.value,
            "lifecycle_reason": self.lifecycle_reason,
            "pass_l1": self.pass_l1,
            "l1_verdict": self.l1_verdict,
            "l1_absolute_reds": "|".join(self.l1_absolute_reds),
            "l1_conditional_reds": "|".join(self.l1_conditional_reds),
            "l1_red_flags": "|".join(self.l1_red_flags),
            "revenue_cagr_3y": self.revenue_cagr_3y,
            "deducted_yoy": self.deducted_yoy,
            "revenue_yoy": self.revenue_yoy,
            "ocf_profit_ratio_3y": self.ocf_profit_ratio_3y,
            "goodwill_ratio": self.goodwill_ratio,
            "score_l2": self.score_l2,
            "gross_margin_trend": self.gross_margin_trend,
            "expense_leverage": self.expense_leverage,
            "contract_liab_growth": self.contract_liab_growth,
            "rd_ratio": self.rd_ratio,
            "score_l3": self.score_l3,
            "roic": self.roic,
            "roic_ttm": self.roic_ttm,
            "wacc": self.wacc,
            "roic_minus_wacc": self.roic_minus_wacc,
            "roe": self.roe,
            "fcf_per_share": self.fcf_per_share,
            "debt_ratio": self.debt_ratio,
            "score_l4": self.score_l4,
            "industry_weighted_pct": self.industry_weighted_pct,
            "score_l5": self.score_l5,
            "peg": self.peg,
            "pe_percentile": self.pe_percentile,
            "growth_accel": self.growth_accel,
            "composite_score": self.composite_score,
            "quality_score": self.quality_score,
            "l5_status": self.l5_status,
            "decision": self.decision,
            "stock_regime": self.stock_regime,
            "capex_phase": self.capex_phase,
            "persistence_score": self.persistence_score,
            "is_growth_eligible": self.is_growth_eligible,
            "block_reason": self.block_reason,
            "_saved_weights": self._saved_weights,
        }

    @staticmethod
    def csv_columns() -> list:
        return list(GrowthScorecard().to_dict().keys())


def normalize_pool(results: list[dict]) -> list[dict]:
    """候选池截面排名标准化。

    对 L2/L3/L5 在候选池内做百分位排名，
    消除层间方差差异，让权重设计恢复诚实。

    L1 不参与标准化（它是惩罚/gate，不是分数维度）。
    L4 不参与标准化（它已经是行业百分位产物）。
    """
    if len(results) < 5:
        return results  # 样本太少，不做标准化

    # 提取各层原始分
    def _safe_score(r, key):
        v = r.get(key, np.nan)
        return v if not np.isnan(v) and v is not None else None

    layers = {
        "score_l2": [_safe_score(r, "score_l2") for r in results],
        "score_l3": [_safe_score(r, "score_l3") for r in results],
        "score_l5": [_safe_score(r, "score_l5") for r in results],
    }

    # 计算百分位排名 (0-1)
    ranks = {}
    for layer, vals in layers.items():
        valid = [(i, v) for i, v in enumerate(vals) if v is not None]
        if len(valid) < 3:
            continue
        sorted_vals = sorted(v for _, v in valid)
        n = len(sorted_vals)
        rank_map = {}
        for orig_i, v in valid:
            # 百分位: 严格小于的占比（0=最差, 1=最好）
            pct = sum(1 for x in sorted_vals if x < v) / n
            # 拉伸到 [0.05, 0.95] 防止极端
            pct = 0.05 + pct * 0.90
            rank_map[orig_i] = round(pct, 4)
        ranks[layer] = rank_map

    # 写入 rank 字段
    for layer, rank_map in ranks.items():
        rank_key = layer + "_rank"
        for i, r in enumerate(results):
            r[rank_key] = rank_map.get(i, 0.5)

    return results


def compute_composite(
    card: GrowthScorecard,
    funnel_result: dict,
    weight_mode: str = "lifecycle",
) -> GrowthScorecard:
    """计算综合得分并填充打分卡。

    v3.0: Regime 路由替代生命周期权重 — Regime 决定的不只是权重，
    而是整个评估框架（估值框架/权重矩阵/决策上限/叙事标签）。
    """
    from growth_os.config import REGIME_WEIGHTS as MARKET_REGIME_WEIGHTS
    from growth_os.config import COMMODITY_INDUSTRIES

    l1 = funnel_result.get("l1_details", {})
    l2 = funnel_result.get("l2_details", {})
    l3 = funnel_result.get("l3_details", {})
    l4 = funnel_result.get("l4_details", {})
    l5 = funnel_result.get("l5_details", {})

    # 先计算成长资格门（ROIC<WACC且营收负增长），供 Regime 路由使用
    roic_wacc_val = l3.get("roic_vs_wacc", {}).get("value", {})
    spread = roic_wacc_val.get("spread") if roic_wacc_val else None
    rev_yoy_val = l1.get("deducted_vs_revenue", {}).get("value", {}).get("revenue")
    roic_below_wacc = spread is not None and spread < 0
    _is_growth_eligible = not (
        roic_below_wacc and rev_yoy_val is not None and rev_yoy_val < 0
    )

    # 检查是否为商品驱动行业
    industry = card.industry_l3 or ""
    _is_commodity = any(kw in industry for kw in COMMODITY_INDUSTRIES)

    # v3.0: Regime 路由 — 替代生命周期权重
    route = classify_regime(
        lifecycle=card.lifecycle,
        is_growth_eligible=_is_growth_eligible,
        pass_l1=card.pass_l1,
        is_commodity=_is_commodity,
        lifecycle_reason=card.lifecycle_reason,
        capex_phase=card.capex_phase,
    )
    card.stock_regime = route.regime.value
    card.is_growth_eligible = route.growth_eligible
    card.block_reason = route.report_note

    # 不入池的 Regime（权重全零）：直接返回
    if route.decision_ceiling.value in ("一票否决", "高风险观察池"):
        card.composite_score = 0
        card.decision = regime_decision(route, 0)
        card._saved_weights = route.weight_matrix
        return card

    # L0 市场 Regime 权重覆盖（保留，但作用于 Regime 内部权重调整）
    if weight_mode != "lifecycle" and weight_mode in MARKET_REGIME_WEIGHTS:
        weights = MARKET_REGIME_WEIGHTS[weight_mode]
    else:
        weights = route.weight_matrix

    card._saved_weights = weights

    # 填充 A 区: L1 verdict + red flag classification
    card.l1_verdict = funnel_result.get("l1_verdict", "")
    card.l1_absolute_reds = funnel_result.get("l1_absolute_reds", [])
    card.l1_conditional_reds = funnel_result.get("l1_conditional_reds", [])
    card.revenue_cagr_3y = l1.get("revenue_cagr_3y", {}).get("value")
    card.deducted_yoy = l1.get("deducted_vs_revenue", {}).get("value", {}).get("deducted")
    card.revenue_yoy = l1.get("deducted_vs_revenue", {}).get("value", {}).get("revenue")
    card.ocf_profit_ratio_3y = l1.get("ocf_profit_ratio_3y", {}).get("value")
    card.goodwill_ratio = l1.get("goodwill_ratio", {}).get("value")

    # 填充 B 区
    card.gross_margin_trend = l2.get("gross_margin_trend", {}).get("label", "")
    card.expense_leverage = l2.get("expense_leverage", {}).get("label", "")
    card.rd_ratio = l2.get("rd_intensity", {}).get("value")
    # 合同负债
    cl = l2.get("contract_liabilities", {})
    card.contract_liab_growth = cl.get("value") if cl.get("value") is not None else None

    # 填充 C 区
    roic_wacc = l3.get("roic_vs_wacc", {}).get("value", {})
    if isinstance(roic_wacc, dict):
        card.roic = roic_wacc.get("roic")
        card.roic_ttm = roic_wacc.get("roic") if roic_wacc.get("roic_ttm") else None
        card.wacc = roic_wacc.get("wacc")
        card.roic_minus_wacc = roic_wacc.get("spread")
    card.roe = l3.get("roe_quality", {}).get("value")
    card.fcf_per_share = l3.get("fcf_trend", {}).get("value")
    debt = l3.get("debt_safety", {}).get("value", {})
    if isinstance(debt, dict):
        card.debt_ratio = debt.get("debt_ratio")

    # 填充 D 区: 行业校准
    card.industry_weighted_pct = l4.get("weighted_percentile", {}).get("value")

    # 填充 E 区: 预期差
    card.peg = l5.get("peg_ratio", {}).get("value")
    card.pe_percentile = l5.get("pe_percentile", {}).get("value")
    card.growth_accel = l5.get("growth_acceleration", {}).get("label", "")

    # 综合得分 (0-100)
    # 五层加权: L1_risk + L2_moat + L3_efficiency + L4_industry + L5_expectation
    # 优先使用截面排名分 (rank%)，消除层间方差差异

    # --- L5 数据完整性检测 ---
    peg_val = l5.get("peg_ratio", {}).get("value")
    peg_gproxy = l5.get("peg_ratio", {}).get("g_proxy")
    ga_score = l5.get("growth_acceleration", {}).get("score", 0)
    ga_score = ga_score if not (ga_score is None or (isinstance(ga_score, float) and np.isnan(ga_score))) else 0

    if peg_val is not None and peg_gproxy is not None:
        l5_status = L5Status.OK
    elif ga_score > 0:
        l5_status = L5Status.PARTIAL
    else:
        l5_status = L5Status.MISSING

    use_ranks = (funnel_result.get("score_l2_rank") is not None)

    if use_ranks:
        rank_l2 = funnel_result.get("score_l2_rank", 0.5)
        rank_l3 = funnel_result.get("score_l3_rank", 0.5)
        rank_l5 = funnel_result.get("score_l5_rank", 0.5)
        s2 = rank_l2 * 10
        s3 = rank_l3 * 10
        s5 = rank_l5 * 10
    else:
        s2 = card.score_l2 if not np.isnan(card.score_l2) else 0
        s3 = card.score_l3 if not np.isnan(card.score_l3) else 0
        s5 = card.score_l5 if not np.isnan(card.score_l5) else 0

    s4 = card.score_l4 if not np.isnan(card.score_l4) else 0

    # L5 上限锁定（PARTIAL 时上限 5/10）
    if l5_status == L5Status.PARTIAL:
        s5 = min(s5, 5.0)

    # 排雷风险分: 每触发一个红灯扣1分, 最多扣到0
    l1_risk_score = max(0, 10 - len(card.l1_red_flags))

    if l5_status == L5Status.MISSING:
        # L5 不参与，L1-L4 权重重归一化
        w1234 = {
            "L1_risk": weights["L1_risk"],
            "L2_moat": weights["L2_moat"],
            "L3_efficiency": weights["L3_efficiency"],
            "L4_industry": weights["L4_industry"],
        }
        w_sum = sum(w1234.values())
        composite = (
            l1_risk_score * (w1234["L1_risk"] / w_sum) * 10 +
            s2 * (w1234["L2_moat"] / w_sum) * 10 +
            s3 * (w1234["L3_efficiency"] / w_sum) * 10 +
            s4 * (w1234["L4_industry"] / w_sum) * 10
        )
    else:
        composite = (
            l1_risk_score * weights["L1_risk"] * 10 +
            s2 * weights["L2_moat"] * 10 +
            s3 * weights["L3_efficiency"] * 10 +
            s4 * weights["L4_industry"] * 10 +
            s5 * weights["L5_expectation"] * 10
        )

    card.composite_score = round(composite, 1)
    card.l5_status = l5_status.value

    # 成长质量分（L1-L4，不含L5估值）
    q_weights = {
        "L1_risk": weights["L1_risk"], "L2_moat": weights["L2_moat"],
        "L3_efficiency": weights["L3_efficiency"], "L4_industry": weights["L4_industry"],
    }
    q_sum = sum(q_weights.values())
    quality = (
        l1_risk_score * (q_weights["L1_risk"] / q_sum) * 10 +
        s2 * (q_weights["L2_moat"] / q_sum) * 10 +
        s3 * (q_weights["L3_efficiency"] / q_sum) * 10 +
        s4 * (q_weights["L4_industry"] / q_sum) * 10
    )
    card.quality_score = round(quality, 1)

    # v3.0: Regime 路由统一决策 — 替代零散的条件判断树
    # Regime 已内置: 成长资格门 / 衰退期降级 / 商品脉冲检测 / L1否决
    card.decision = regime_decision(route, card.composite_score)

    # L5 估值框架标签（供 report.py 使用）
    # 由 Regime 决定 PEG 是否适用，写入 funnel_result 供下游读取
    if not route.peg_applicable:
        l5_label = funnel_result.get("l5_details", {}).get("peg_ratio", {}).get("label", "")
        if l5_label and "PEG" in str(l5_label):
            funnel_result["_peg_overridden"] = True
            funnel_result["_peg_note"] = (
                f"⛔ PEG框架不适用({route.regime.value}) — "
                f"建议使用{route.valuation_framework.value}框架"
            )

    return card


def recalc_composite_with_ranks(r: dict) -> float:
    """用截面排名分重新计算综合分（供 normalize_pool 后使用）。

    使用 compute_composite 保存的权重，不重复触发 tracker。
    """
    weights = r.get("_saved_weights")
    if weights is None:
        return r.get("composite_score", 0)
    if not isinstance(weights, dict):
        return r.get("composite_score", 0)

    rank_l2 = r.get("score_l2_rank", 0.5)
    rank_l3 = r.get("score_l3_rank", 0.5)
    rank_l5 = r.get("score_l5_rank", 0.5)

    s4_raw = r.get("score_l4", 0)
    if s4_raw is None or (isinstance(s4_raw, float) and np.isnan(s4_raw)):
        s4 = 0
    else:
        s4 = s4_raw

    red_flags_str = r.get("l1_red_flags", "")
    red_count = len([x for x in red_flags_str.split("|") if x]) if red_flags_str else 0
    l1_risk = max(0, 10 - red_count)

    try:
        composite = (
            l1_risk * weights.get("L1_risk", 0.2) * 10 +
            rank_l2 * 10 * weights.get("L2_moat", 0.3) * 10 +
            rank_l3 * 10 * weights.get("L3_efficiency", 0.25) * 10 +
            s4 * weights.get("L4_industry", 0.15) * 10 +
            rank_l5 * 10 * weights.get("L5_expectation", 0.1) * 10
        )
    except Exception:
        return r.get("composite_score", 0)
    return round(composite, 1)
