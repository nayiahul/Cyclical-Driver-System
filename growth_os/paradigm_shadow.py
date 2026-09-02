"""Paradigm Shadow Layer v1 — P_AI_OPTICAL_CYCLE Shadow Mode 接入 (Step 11-D)。

原则: shadow_only=True — 只附加标签, 不改变 L/E Priority 决策。
用途: 30 天沙盒观察 P 标签是否改善人工判断质量 (无污染验证)。

插件: P_AI_OPTICAL_CYCLE (窄入口, 已过 C6 四验收)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from pit.market import MarketData
from growth_os.growth_probes import probe_margin_resilience

# 窄入口: 光模块/光通信核心 (SW3 级)
AI_OPTICAL_CORE = {
    "300308": "中际旭创", "300502": "新易盛", "002281": "光迅科技",
    "300394": "天孚通信", "300620": "光库科技", "688048": "长光华芯",
    "300548": "博创科技", "603083": "剑桥科技",
}

# P Thesis Broken (毛利探针转红 = 核心证伪, C6-C 验证)
BROKEN_GROSS_MARGIN = 0.5  # margin 探针 < green 阈值


@dataclass
class ParadigmShadowResult:
    code: str
    paradigm: str            # "AI_OPTICAL_CYCLE" | ""
    p_state: str             # P0-P4
    shadow_only: bool = True
    evidence: list = field(default_factory=list)
    broken_flags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "code": self.code, "paradigm": self.paradigm,
            "p_state": self.p_state, "shadow_only": self.shadow_only,
            "p_evidence": self.evidence, "p_broken": self.broken_flags,
        }


class ParadigmShadowLayer:
    """P 层 Shadow 标注器 v1 (只观察, 不决策)。"""

    def __init__(self):
        self._mkt = MarketData()

    def evaluate(self, code: str, t_date: str,
                 discovery: float = None) -> ParadigmShadowResult:
        """单只标注。discovery 由外部传入 (0-1 探针综合)。"""
        if code not in AI_OPTICAL_CORE:
            return ParadigmShadowResult(code, "", "P0")

        # 毛利状态 (C6-C: 核心证伪变量)
        m = probe_margin_resilience(code, t_date)
        margin_green = m["level"] == "green"
        margin_level = m["level"]

        evidence = [f"光模块核心({AI_OPTICAL_CORE[code]})"]
        broken = []
        if margin_level == "red":
            broken.append("毛利探针转红(Broken)")
        elif margin_level == "yellow":
            broken.append("毛利yellow(观察)")

        # P 状态: 订单兑现(discovery) + 毛利保持
        if discovery is None or discovery >= 0.5:
            if margin_green:
                p_state = "P2"  # 兑现期: 订单+毛利双确认
            elif margin_level == "yellow":
                p_state = "P1"  # 需求期: 订单好但毛利待确认
            else:
                p_state = "P0"  # Broken: 毛利恶化
                broken.append("P2→P0 降级(毛利证伪)")
            evidence.append(f"discovery={discovery:.2f}" if discovery else "discovery≥0.5")
        else:
            p_state = "P1" if margin_green else "P0"

        evidence.append(f"毛利探针={margin_level}")
        if margin_green:
            evidence.append("毛利保持(硬条件满足)")

        return ParadigmShadowResult(
            code, "AI_OPTICAL_CYCLE", p_state,
            evidence=evidence, broken_flags=broken)

    def annotate(self, df: pd.DataFrame, t_date: str,
                 discovery_map: dict = None) -> pd.DataFrame:
        """批量标注: 附加 paradigm/p_state/evidence 列, 不改任何现有列。"""
        out = df.copy()
        codes = out["code"].astype(str).str.zfill(6).tolist()
        paradigms, p_states, evs, brokens = [], [], [], []
        for c in codes:
            r = self.evaluate(c, t_date,
                              discovery_map.get(c) if discovery_map else None)
            paradigms.append(r.paradigm)
            p_states.append(r.p_state)
            evs.append("; ".join(r.evidence))
            brokens.append("; ".join(r.broken_flags))
        out["paradigm"] = paradigms
        out["p_state"] = p_states
        out["p_evidence"] = evs
        out["p_broken"] = brokens
        return out
