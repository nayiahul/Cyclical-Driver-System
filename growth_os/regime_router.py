"""个股 Regime 路由引擎 — v3.0 状态机核心。

将"生命周期→权重"升级为"Regime→评估框架→决策"。

Regime 决定的不只是权重，而是：
  - 估值框架（PEG / PB-ROE / PE分位 / 不适用）
  - 权重矩阵（哪些维度在当前 Regime 下有意义）
  - 决策模板（深度研究 / 周期跟踪 / 一票否决）
  - 报告模板（成长叙事 / 周期叙事 / 商品叙事）

三空间分离：
  Space A (Eligibility): L1 pass_l1 → 硬闸
  Space B (Quality): L2+L3+L4 → Regime 特定评分
  Space C (Expectation): L5 → Regime 特定估值框架

Top20 = argmax(B + C | A == pass)
"""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class StockRegime(Enum):
    """个股 Regime 分类 — 决定适用什么评估框架。"""
    GROWTH_ACCELERATION = "成长加速期"
    GROWTH_MATURE = "成长成熟期"
    GROWTH_INTRODUCTION = "导入期"
    CYCLICAL_TRANSITION = "周期过渡态"
    CYCLICAL_DECLINE = "周期出清"
    COMMODITY_DRIVEN = "商品驱动"
    VALUE_TRAP = "排雷未通过"


class ValuationFramework(Enum):
    """Regime 对应的估值框架。"""
    PEG = "PEG"               # 成长股 PEG 估值
    PE_PERCENTILE = "PE分位"   # 成熟股 PE 历史分位
    GROWTH_ACCEL = "增长加速度"  # 导入期，尚无利润，看营收加速度
    PB_ROE = "PB-ROE"         # 周期股 PB-ROE
    NOT_APPLICABLE = "不适用"   # 价值陷阱 / 商品驱动


class DecisionTemplate(Enum):
    """Regime 对应的决策模板。"""
    GROWTH_DEEP = "深度研究"              # 可重仓成长
    GROWTH_WATCH = "加入观察池"           # 成长待观察
    GROWTH_SKIP = "暂不关注"              # 成长池外
    CYCLE_TRACK = "周期跟踪"              # 非成长持仓，跟踪周期位置
    HIGH_RISK = "高风险观察池"             # 高风险，不入池
    VETO = "一票否决"                     # 硬伤，不可投


@dataclass
class RegimeRoute:
    """Regime 路由结果 — 包含该 Regime 下的完整评估框架。"""
    regime: StockRegime
    valuation_framework: ValuationFramework
    weight_matrix: dict  # {L1_risk, L2_moat, L3_efficiency, L4_industry, L5_expectation}
    growth_eligible: bool  # 是否具备成长持仓资格
    peg_applicable: bool   # PEG 框架是否适用
    decision_ceiling: DecisionTemplate  # 该 Regime 下最高可达的决策等级
    narrative: str         # 报告叙事标签
    report_note: str       # 报告附注
    space_b_disabled: list[str] = field(default_factory=list)  # Space B 中禁用的子维度
    capex_alert: str = ""  # CAPEX 周期预警（空=无预警）
    industry_cycle: str = ""  # 产业周期阶段 expansion/neutral/contraction


# ═══════════════════════════════════════════════
# Regime 权重矩阵
# ═══════════════════════════════════════════════

REGIME_WEIGHTS = {
    StockRegime.GROWTH_ACCELERATION: {
        "L1_risk": 0.20, "L2_moat": 0.30, "L3_efficiency": 0.25,
        "L4_industry": 0.15, "L5_expectation": 0.10,
    },
    StockRegime.GROWTH_MATURE: {
        "L1_risk": 0.15, "L2_moat": 0.20, "L3_efficiency": 0.40,
        "L4_industry": 0.15, "L5_expectation": 0.10,
    },
    StockRegime.GROWTH_INTRODUCTION: {
        "L1_risk": 0.10, "L2_moat": 0.30, "L3_efficiency": 0.10,
        "L4_industry": 0.35, "L5_expectation": 0.15,
    },
    StockRegime.CYCLICAL_TRANSITION: {
        "L1_risk": 0.25, "L2_moat": 0.15, "L3_efficiency": 0.30,
        "L4_industry": 0.20, "L5_expectation": 0.10,
    },
    StockRegime.CYCLICAL_DECLINE: {
        # 衰退期：无有效权重，不入池
        "L1_risk": 0.0, "L2_moat": 0.0, "L3_efficiency": 0.0,
        "L4_industry": 0.0, "L5_expectation": 0.0,
    },
    StockRegime.COMMODITY_DRIVEN: {
        # 商品驱动：不入成长池
        "L1_risk": 0.0, "L2_moat": 0.0, "L3_efficiency": 0.0,
        "L4_industry": 0.0, "L5_expectation": 0.0,
    },
    StockRegime.VALUE_TRAP: {
        # 价值陷阱：不入池
        "L1_risk": 0.0, "L2_moat": 0.0, "L3_efficiency": 0.0,
        "L4_industry": 0.0, "L5_expectation": 0.0,
    },
}

# ═══════════════════════════════════════════════
# Regime 路由规则
# ═══════════════════════════════════════════════

REGIME_ROUTES: dict[StockRegime, RegimeRoute] = {
    StockRegime.GROWTH_ACCELERATION: RegimeRoute(
        regime=StockRegime.GROWTH_ACCELERATION,
        valuation_framework=ValuationFramework.PEG,
        weight_matrix=REGIME_WEIGHTS[StockRegime.GROWTH_ACCELERATION],
        growth_eligible=True,
        peg_applicable=True,
        decision_ceiling=DecisionTemplate.GROWTH_DEEP,
        narrative="成长加速",
        space_b_disabled=[],
        report_note="飞轮加速期，PEG框架完全适用。关注营收加速度和ROIC趋势。",
    ),
    StockRegime.GROWTH_MATURE: RegimeRoute(
        regime=StockRegime.GROWTH_MATURE,
        valuation_framework=ValuationFramework.PE_PERCENTILE,
        weight_matrix=REGIME_WEIGHTS[StockRegime.GROWTH_MATURE],
        growth_eligible=True,
        peg_applicable=False,
        decision_ceiling=DecisionTemplate.GROWTH_DEEP,
        narrative="成长成熟",
        space_b_disabled=[],
        report_note="成熟期成长股，ROIC>WACC为核心优势。PEG框架部分适用，优先看PE历史分位。",
    ),
    StockRegime.GROWTH_INTRODUCTION: RegimeRoute(
        regime=StockRegime.GROWTH_INTRODUCTION,
        valuation_framework=ValuationFramework.GROWTH_ACCEL,
        weight_matrix=REGIME_WEIGHTS[StockRegime.GROWTH_INTRODUCTION],
        growth_eligible=True,
        peg_applicable=False,
        decision_ceiling=DecisionTemplate.GROWTH_WATCH,
        narrative="早期导入",
        space_b_disabled=["expense_leverage"],  # 导入期费用率高是正常的
        report_note="导入期，尚未盈利或微利。估值看营收加速度和行业位置，PEG不适用。",
    ),
    StockRegime.CYCLICAL_TRANSITION: RegimeRoute(
        regime=StockRegime.CYCLICAL_TRANSITION,
        valuation_framework=ValuationFramework.PB_ROE,
        weight_matrix=REGIME_WEIGHTS[StockRegime.CYCLICAL_TRANSITION],
        growth_eligible=False,
        peg_applicable=False,
        decision_ceiling=DecisionTemplate.CYCLE_TRACK,
        narrative="周期过渡",
        space_b_disabled=[],
        report_note="ROIC<WACC或营收负增长，处于周期/出清过渡态。PEG框架不适用，建议用PB-ROE或周期调整估值。仓位不超过成长组合1/3。",
    ),
    StockRegime.CYCLICAL_DECLINE: RegimeRoute(
        regime=StockRegime.CYCLICAL_DECLINE,
        valuation_framework=ValuationFramework.NOT_APPLICABLE,
        weight_matrix=REGIME_WEIGHTS[StockRegime.CYCLICAL_DECLINE],
        growth_eligible=False,
        peg_applicable=False,
        decision_ceiling=DecisionTemplate.HIGH_RISK,
        narrative="周期出清",
        space_b_disabled=[],
        report_note="衰退期，毛利率连续下滑+辅助恶化信号。不入成长池，跟踪周期位置等待反转信号。",
    ),
    StockRegime.COMMODITY_DRIVEN: RegimeRoute(
        regime=StockRegime.COMMODITY_DRIVEN,
        valuation_framework=ValuationFramework.NOT_APPLICABLE,
        weight_matrix=REGIME_WEIGHTS[StockRegime.COMMODITY_DRIVEN],
        growth_eligible=False,
        peg_applicable=False,
        decision_ceiling=DecisionTemplate.CYCLE_TRACK,
        narrative="商品驱动",
        space_b_disabled=[],
        report_note="营收/利润增长来自商品价格而非组织扩张。商品周期框架，不入成长池。",
    ),
    StockRegime.VALUE_TRAP: RegimeRoute(
        regime=StockRegime.VALUE_TRAP,
        valuation_framework=ValuationFramework.NOT_APPLICABLE,
        weight_matrix=REGIME_WEIGHTS[StockRegime.VALUE_TRAP],
        growth_eligible=False,
        peg_applicable=False,
        decision_ceiling=DecisionTemplate.VETO,
        narrative="排雷未通过",
        space_b_disabled=[],
        report_note="L1排雷未通过，存在硬伤。不入成长池，需人工复核排雷事项。",
    ),
}


# ═══════════════════════════════════════════════
# 路由函数
# ═══════════════════════════════════════════════

def classify_regime(
    lifecycle,
    is_growth_eligible: bool,
    pass_l1: bool,
    is_commodity: bool = False,
    lifecycle_reason: str = "",
    capex_phase: str = "",
) -> RegimeRoute:
    """根据信号组合判定个股 Regime，返回完整路由。

    优先级（从高到低）：
    1. L1 不通过 → VALUE_TRAP
    2. 商品驱动 → COMMODITY_DRIVEN
    3. 生命周期衰退 → CYCLICAL_DECLINE
    4. 成长资格未通过 → CYCLICAL_TRANSITION
    5. 生命周期路由 → GROWTH_ACCELERATION / GROWTH_MATURE / GROWTH_INTRODUCTION

    CAPEX 周期信号作为路由结果的风险标记（不改变 Regime 分类，但附加预警）。
    """
    from growth_os.config import LifecycleStage

    # 1. L1 排雷未通过 → 不入池
    if not pass_l1:
        return REGIME_ROUTES[StockRegime.VALUE_TRAP]

    # 2. 商品驱动 → 不入成长池
    if is_commodity or "商品脉冲" in lifecycle_reason:
        return REGIME_ROUTES[StockRegime.COMMODITY_DRIVEN]

    # 3. 周期出清
    if lifecycle == LifecycleStage.DECLINE:
        return REGIME_ROUTES[StockRegime.CYCLICAL_DECLINE]

    # 4. 成长资格未通过 → 周期过渡
    if not is_growth_eligible:
        route = REGIME_ROUTES[StockRegime.CYCLICAL_TRANSITION]
        # CAPEX 复苏信号：提示接近周期底部
        if capex_phase in ("recovery",):
            route.capex_alert = f"CAPEX复苏信号({capex_phase})：营收改善+CAPEX未增→产能利用率提升，关注反转"
        return route

    # 5. 生命周期路由 + CAPEX 预警
    if lifecycle == LifecycleStage.ACCELERATION:
        route = REGIME_ROUTES[StockRegime.GROWTH_ACCELERATION]
    elif lifecycle == LifecycleStage.MATURITY:
        route = REGIME_ROUTES[StockRegime.GROWTH_MATURE]
    elif lifecycle == LifecycleStage.INTRODUCTION:
        route = REGIME_ROUTES[StockRegime.GROWTH_INTRODUCTION]
    else:
        route = REGIME_ROUTES[StockRegime.CYCLICAL_TRANSITION]

    # CAPEX 预警：成长股在产能过剩/收缩区 → 风险标记
    if capex_phase in ("danger",):
        route.capex_alert = f"产能过剩预警(CAPEX={capex_phase})：CAPEX扩张但营收未跟上，警惕周期顶部"
    elif capex_phase in ("contraction",):
        route.capex_alert = f"CAPEX收缩({capex_phase})：主动或被动缩减开支，关注是否进入衰退"

    return route


def regime_decision(route: RegimeRoute, composite_score: float) -> str:
    """根据 Regime 路由和综合分，输出最终决策。

    Regime 的 decision_ceiling 限制了该 Regime 下能达到的最高决策等级。
    例如 CYCLICAL_TRANSITION 的 ceiling 是 CYCLE_TRACK，
    即使 composite_score >= 70 也不会标为"深度研究"。
    """
    ceiling = route.decision_ceiling

    # 不入池的 Regime 直接返回固定决策
    if ceiling == DecisionTemplate.VETO:
        return "一票否决"
    if ceiling == DecisionTemplate.HIGH_RISK:
        return "高风险观察池(衰退期)"
    if ceiling == DecisionTemplate.CYCLE_TRACK:
        if "商品" in route.narrative:
            return "周期跟踪(商品驱动)"
        return "周期跟踪(非成长持仓)"

    # 可入池的 Regime：正常打分+阈值
    if composite_score >= 70:
        return "深度研究"
    elif composite_score >= 50:
        return "加入观察池"
    else:
        return "暂不关注"
