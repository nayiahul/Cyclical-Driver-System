"""Sprint 12+18+19: Persistence × Composite → 仓位建议。

双维度矩阵: Composite(漏斗质量) × Persistence(增长持续性)
不替代Composite,只做独立信息层叠加。

Sprint 18: 修复映射矛盾 — weight/hold/action 由 MATRIX label 统一派生。
Sprint 19: 仓位双因子校验 — L1排雷层 + Growth Source驱动力 传导到仓位。
"""

# Sprint 18: 仓位标签 → 执行参数自洽映射
LABEL_CONFIG = {
    "核心": {"weight": "8-15%", "hold": "18-24个月", "action": "越跌越买"},
    "标配": {"weight": "4-8%",  "hold": "12-18个月", "action": "持有为主"},
    "轻仓": {"weight": "<2%",   "hold": "1-3个月",   "action": "快进快出"},
    "观察": {"weight": "<2%",   "hold": "3-6个月",   "action": "跟踪待确认"},
    "规避": {"weight": "0%",    "hold": "N/A",       "action": "不参与"},
}

# Sprint 19: L1 review 降级映射
LABEL_DOWNGRADE = {
    "核心": "标配",
    "标配": "轻仓",
    "轻仓": "观察",
    "观察": "观察",
    "规避": "规避",
}

# 双维度矩阵: rows=Composite档(1-5), cols=Persistence档(1-5)
# 值: (仓位label, 理由)
MATRIX = [
    # Pers:  1        2          3          4          5
    [("规避","双低"),("规避","双低"),("规避","双低"),("规避","双低"),("观察","低质高潜")],  # C1
    [("规避","双低"),("规避","双低"),("轻仓",""),("轻仓",""),("标配","质量待释放")],        # C2
    [("规避","双低"),("轻仓",""),("轻仓",""),("标配",""),("标配","持续性支撑")],             # C3
    [("轻仓","高质低持"),("标配",""),("标配",""),("核心","高质高持"),("核心","高质高持")],   # C4
    [("标配",""),("标配",""),("核心","高质高持"),("核心","高质高持"),("核心","高质高持")],   # C5
]


def recommend(composite: float, persistence: int,
              l1_verdict: str = "pass", source: str = "",
              max_composite: float = 95.0) -> dict:
    """双因子仓位建议。新增 L1 排雷层 + Growth Source 驱动力校验。

    Args:
        composite: 综合评分
        persistence: 增长持续性 1-5
        l1_verdict: L1 排雷判定 ("pass" / "review")
        source: 增长驱动力标签 (tech_penetration / price_cycle / ...)
    """
    c = min(5, max(1, int(composite / max_composite * 5) + 1)) if max_composite > 0 else 3
    p = max(1, min(5, persistence))
    label, rationale = MATRIX[c - 1][p - 1]
    tags = []

    # ── 规则 B: 低持续性封顶 → max "轻仓" ──
    if p <= 2 and label not in ("观察", "规避"):
        label = "轻仓"
        tags.append("低持续性(p≤2)封顶轻仓")

    # ── 规则 C: price_cycle 封顶 → max "轻仓" ──
    if source == "price_cycle" and label not in ("观察", "规避"):
        label = "轻仓"
        tags.append("price_cycle封顶轻仓")

    # ── 规则 A: L1 review 降一级 ──
    if l1_verdict == "review":
        label = LABEL_DOWNGRADE.get(label, label)
        tags.append("L1 review降级")

    # 确保非周期/非低持续标的降级后不低于"轻仓"
    if label in ("观察", "规避") and p > 2 and source != "price_cycle":
        label = "轻仓"

    cfg = LABEL_CONFIG[label]
    full_rationale = rationale or f"Composite{c}/Persist{p}"
    if tags:
        full_rationale += " | " + " + ".join(tags)

    return {
        "composite_bucket": c, "persistence": p,
        "position": label, "weight": cfg["weight"],
        "hold": cfg["hold"], "action": cfg["action"],
        "rationale": full_rationale,
    }
