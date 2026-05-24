"""打分卡 — GrowthScorecard 数据结构与综合评分计算。"""
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from growth_os.config import LifecycleStage
from growth_os.lifecycle import get_weights


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
        }

    @staticmethod
    def csv_columns() -> list:
        return list(GrowthScorecard().to_dict().keys())


def compute_composite(
    card: GrowthScorecard,
    funnel_result: dict,
) -> GrowthScorecard:
    """计算综合得分并填充打分卡。

    综合得分 = L1*w1 + L2*w2 + L3*w3 + L4*w4 + L5*w5
    权重由生命周期阶段决定，每层原始分0-10，权重和=1.0，满分100。
    """
    weights = get_weights(card.lifecycle)
    if weights is None:
        # 衰退期: 不淘汰，降级为高风险观察池
        card.composite_score = 0
        card.decision = "高风险观察池(衰退期)"
        return card

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
    score_l2 = card.score_l2 if not np.isnan(card.score_l2) else 0
    score_l3 = card.score_l3 if not np.isnan(card.score_l3) else 0
    score_l4 = card.score_l4 if not np.isnan(card.score_l4) else 0
    score_l5 = card.score_l5 if not np.isnan(card.score_l5) else 0

    # 排雷风险分: 每触发一个红灯扣1分, 最多扣到0
    l1_risk_score = max(0, 10 - len(card.l1_red_flags))

    composite = (
        l1_risk_score * weights["L1_risk"] * 10 +
        score_l2 * weights["L2_moat"] * 10 +
        score_l3 * weights["L3_efficiency"] * 10 +
        score_l4 * weights["L4_industry"] * 10 +
        score_l5 * weights["L5_expectation"] * 10
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
