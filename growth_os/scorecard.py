"""打分卡 — GrowthScorecard 数据结构与综合评分计算。"""
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from growth_os.config import LifecycleStage
from growth_os.lifecycle import get_weights, resolve_weights


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
    decision: str = ""
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
            "decision": self.decision,
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

    综合得分 = L1*w1 + L2*w2 + L3*w3 + L4*w4 + L5*w5
    权重由生命周期阶段决定，每层原始分0-10，权重和=1.0，满分100。

    Args:
        weight_mode: "lifecycle"(默认) | "defensive" | "maturity_forced"
                     非 lifecycle 时使用 REGIME_WEIGHTS 替代生命周期权重。
    """
    from growth_os.config import REGIME_WEIGHTS

    # 使用生命周期追踪器（锁定期+混合权重）
    lifecycle_weights = resolve_weights(card.code, card.lifecycle)
    if lifecycle_weights is None:
        card.composite_score = 0
        card.decision = "高风险观察池(衰退期)"
        return card

    # L0 Regime 权重覆盖
    if weight_mode != "lifecycle" and weight_mode in REGIME_WEIGHTS:
        weights = REGIME_WEIGHTS[weight_mode]
    else:
        weights = lifecycle_weights

    # 保存权重供后续标准化重算使用
    card._saved_weights = weights

    l1 = funnel_result.get("l1_details", {})
    l2 = funnel_result.get("l2_details", {})
    l3 = funnel_result.get("l3_details", {})
    l4 = funnel_result.get("l4_details", {})
    l5 = funnel_result.get("l5_details", {})

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
    use_ranks = (funnel_result.get("score_l2_rank") is not None)

    if use_ranks:
        # 用百分位排名 → 映射到 0-10（rank% × 10）
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

    # 排雷风险分: 每触发一个红灯扣1分, 最多扣到0
    l1_risk_score = max(0, 10 - len(card.l1_red_flags))

    composite = (
        l1_risk_score * weights["L1_risk"] * 10 +
        s2 * weights["L2_moat"] * 10 +
        s3 * weights["L3_efficiency"] * 10 +
        s4 * weights["L4_industry"] * 10 +
        s5 * weights["L5_expectation"] * 10
    )

    card.composite_score = round(composite, 1)

    # 决策
    if not card.pass_l1:
        card.decision = "一票否决"
    elif card.composite_score >= 70:
        card.decision = "深度研究"
    elif card.composite_score >= 50:
        card.decision = "加入观察池"
    else:
        card.decision = "暂不关注"

    return card


def recalc_composite_with_ranks(r: dict) -> float:
    """用截面排名分重新计算综合分（供 normalize_pool 后使用）。

    使用 compute_composite 保存的权重，不重复触发 tracker。
    """
    weights = r.get("_saved_weights")
    if weights is None:
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

    composite = (
        l1_risk * weights["L1_risk"] * 10 +
        rank_l2 * 10 * weights["L2_moat"] * 10 +
        rank_l3 * 10 * weights["L3_efficiency"] * 10 +
        s4 * weights["L4_industry"] * 10 +
        rank_l5 * 10 * weights["L5_expectation"] * 10
    )
    return round(composite, 1)
