"""Expectation State Engine v1 — 市场认知状态分类 (Step 9-D2)。

回答: 市场知道多少?
  E0 市场忽略 / E1 少数关注 / E2 市场确认 / E3 一致预期

v0 代理 (已实证 +6pp 增量): RPS 分位
v1 增强: 成交额 Z-score (volume/amount 20日 vs 60日)

输出: 状态标签, 不进评分 — 供 Opportunity Matrix 查表 (Lifecycle v3)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from pit.market import MarketData


@dataclass
class ExpectationResult:
    code: str
    state: str            # E0-E3
    attention: str        # LOW / MEDIUM / HIGH
    rps: Optional[float]
    vol_z: Optional[float]  # 成交额 Z-score
    drivers: list = field(default_factory=list)
    risks: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "code": self.code, "expectation_state": self.state,
            "attention": self.attention, "rps": self.rps,
            "vol_z": self.vol_z,
        }


class ExpectationStateEngine:
    """市场认知状态分类器 v1。"""

    def __init__(self):
        self._mkt = MarketData()

    def classify(self, code: str, t_date: str,
                 rps: Optional[float] = None) -> ExpectationResult:
        """单只分类。rps 由外部传入（需行业截面）；缺省时仅用成交额。"""
        drivers, risks = [], []

        # 成交额 Z-score (20日 vs 60日)
        df = self._mkt.as_of(code, t_date)
        vol_z = None
        if df is not None and len(df) >= 60 and "amount" in df.columns:
            amt = df["amount"].dropna().astype(float)
            if len(amt) >= 60:
                recent = amt.iloc[-20:].mean()
                base = amt.iloc[-60:].mean()
                std = amt.iloc[-60:].std()
                vol_z = float((recent - base) / std) if std > 0 else 0.0
        elif df is not None and len(df) >= 60 and "volume" in df.columns:
            vol = df["volume"].dropna().astype(float)
            if len(vol) >= 60:
                recent = vol.iloc[-20:].mean()
                base = vol.iloc[-60:].mean()
                std = vol.iloc[-60:].std()
                vol_z = float((recent - base) / std) if std > 0 else 0.0

        # E 状态: RPS 为主, 成交额辅助
        if rps is not None:
            if rps >= 80:
                state, attention = "E3", "HIGH"
            elif rps >= 60:
                state, attention = "E2", "HIGH"
            elif rps >= 30:
                # 30-60: 成交额放大 → E1, 否则 E0/E1 边界
                state = "E1" if (vol_z is not None and vol_z > 1.0) else "E1"
                attention = "MEDIUM"
            else:
                state = "E0" if (vol_z is None or vol_z < 1.5) else "E1"
                attention = "LOW"
            drivers.append(f"RPS {rps:.0f}")
        else:
            # 无 RPS: 纯成交额
            if vol_z is not None and vol_z > 2.0:
                state, attention = "E1", "MEDIUM"
            else:
                state, attention = "E0", "LOW"

        if vol_z is not None:
            drivers.append(f"成交额Z={vol_z:+.1f}")
            if vol_z > 2.0:
                risks.append("成交骤增（可能有事件驱动）")
            elif vol_z < -1.0:
                risks.append("成交萎缩（关注度下降）")

        return ExpectationResult(code, state, attention, rps, vol_z,
                                 drivers, risks)

    def classify_many(self, codes: list[str], t_date: str,
                      rps_map: dict = None) -> dict[str, ExpectationResult]:
        out = {}
        for c in codes:
            out[c] = self.classify(c, t_date,
                                   rps_map.get(c) if rps_map else None)
        return out
