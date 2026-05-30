"""Sprint 12: Persistence → 仓位建议。

双维度矩阵: Composite(漏斗质量) × Persistence(增长持续性)
不替代Composite,只做独立信息层叠加。
"""
from typing import Tuple

POSITION_MAP = {
    5: {"label": "核心持仓", "weight": "8-15%", "hold": "18-24个月", "action": "越跌越买"},
    4: {"label": "标配",     "weight": "4-8%",  "hold": "12-18个月", "action": "持有为主"},
    3: {"label": "标配谨慎",  "weight": "2-4%",  "hold": "6-12个月",  "action": "右侧交易"},
    2: {"label": "轻仓交易",  "weight": "<2%",   "hold": "1-3个月",   "action": "快进快出"},
    1: {"label": "规避",     "weight": "0%",    "hold": "N/A",       "action": "禁止左侧"},
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

def recommend(composite: float, persistence: int, max_composite: float = 95.0) -> dict:
    c = min(5, max(1, int(composite / max_composite * 5) + 1)) if max_composite > 0 else 3
    p = max(1, min(5, persistence))
    label, rationale = MATRIX[c - 1][p - 1]
    pos = POSITION_MAP[p]
    return {
        "composite_bucket": c, "persistence": p,
        "position": label, "weight": pos["weight"],
        "hold": pos["hold"], "action": pos["action"],
        "rationale": rationale or f"Composite{c}/Persist{p}",
    }
