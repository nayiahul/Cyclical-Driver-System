"""风格 Regime — 检测成长/价值/均衡风格。

基于市场 PE 趋势:
- PE 上升 → 成长风格占优（市场愿为增长支付溢价）
- PE 下降 → 价值风格占优（市场追求安全边际）
- PE 平稳 → 均衡

在 Market Regime 权重基础上叠加风格偏置:
- GROWTH: 景气度+0.05, 估值-0.05
- VALUE:  估值+0.05, 壁垒+0.05
- BLEND:  不变
"""
import numpy as np


def detect_style(pe_60d_change: float, pe_volatility: float = 0.10) -> str:
    """
    Args:
        pe_60d_change: 全市场 PE 的 60 日变化率
        pe_volatility: PE 变化率的波动阈值

    Returns:
        "GROWTH" | "VALUE" | "BLEND"
    """
    if not np.isnan(pe_60d_change):
        if pe_60d_change > pe_volatility * 0.5:
            return "GROWTH"
        elif pe_60d_change < -pe_volatility * 0.5:
            return "VALUE"
    return "BLEND"


STYLE_WEIGHT_OVERLAY = {
    "GROWTH": {"momentum": 0.05, "moat": 0.00, "valuation": -0.05},
    "VALUE":  {"momentum": -0.05, "moat": 0.05, "valuation": 0.05},
    "BLEND":  {"momentum": 0.00, "moat": 0.00, "valuation": 0.00},
}


def apply_style_overlay(w_m: float, w_b: float, w_v: float,
                        style: str) -> tuple[float, float, float]:
    """在 Market Regime 权重上叠加风格偏置。"""
    overlay = STYLE_WEIGHT_OVERLAY.get(style, STYLE_WEIGHT_OVERLAY["BLEND"])
    w_m += overlay["momentum"]
    w_b += overlay["moat"]
    w_v += overlay["valuation"]
    # 确保非负
    w_m = max(0.10, w_m)
    w_b = max(0.10, w_b)
    w_v = max(0.10, w_v)
    # 归一化
    total = w_m + w_b + w_v
    return w_m / total, w_b / total, w_v / total
