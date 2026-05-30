"""Sprint 16: Cycle State Engine v1.0

从"是什么类型"升级到"在周期哪个位置"。
ROIC波动率 + 动量 + GM趋势 → BOTTOM/UP_TREND/TOP/DOWN
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CycleState:
    state: str   # BOTTOM/UP_TREND/TOP/DOWN/STABLE
    confidence: float
    label: str   # 中文标签
    action: str  # 操作建议


def classify_cycle_state(
    roic: float,
    roic_vol: float,
    gm_trend: str,
    rev_yoy: float,
    roic_momentum: float = 0,
) -> CycleState:
    """四象限周期状态判定。

    ROIC波动率>30pp → 周期股,需要状态判定
    ROIC波动率<15pp → 结构性公司,标为STABLE
    """
    # 低波动 → 结构性公司,不需要周期状态
    if roic_vol < 15:
        return CycleState("STABLE", 0.85, "结构性稳定", "正常持有")

    # 周期状态判定
    rev_high = rev_yoy > 30
    rev_low = rev_yoy < 5
    gm_falling = gm_trend == "下降"
    roic_high = roic > 20
    roic_low = roic < 8
    momentum_positive = roic_momentum > 0

    if roic_high and rev_high and roic_vol > 30:
        # 高ROIC+高增长+高波动 = 周期顶部特征
        if gm_falling:
            return CycleState("TOP", 0.88, "周期顶部(GM已回落)", "减仓/获利了结")
        return CycleState("TOP", 0.80, "周期顶部(高ROIC+高增长)", "警惕反转,逐步减仓")

    if roic_low and rev_low and gm_falling:
        return CycleState("DOWN", 0.85, "周期下行(ROIC+增速双杀)", "规避/空仓")

    if momentum_positive and rev_yoy > 10:
        return CycleState("UP_TREND", 0.75, "周期上行(ROIC改善中)", "持有/适度加仓")

    if roic_low and momentum_positive:
        return CycleState("BOTTOM", 0.70, "周期底部(ROIC低位修复)", "左侧布局/观察")

    return CycleState("UP_TREND", 0.65, "周期上行(趋势确认中)", "标配持有")


def cycle_action_advice(state: CycleState, base_position: str) -> str:
    """根据周期状态调整仓位建议。"""
    if state.state == "TOP":
        return f"⚠️ {state.label} → 建议降仓({base_position}→轻仓)"
    if state.state == "DOWN":
        return f"🔴 {state.label} → 建议清仓观望"
    if state.state == "BOTTOM":
        return f"🔍 {state.label} → 可左侧试探({base_position}维持)"
    if state.state == "UP_TREND":
        return f"🟢 {state.label} → {base_position}持有"
    return base_position
