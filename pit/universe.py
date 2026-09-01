"""UniverseData — 股票池 PIT Provider。

U0（当前实现）: list_date <= t 且当前名称非 ST —— 明确声明存在幸存者偏差。
U1+（数据源 spike 后）: 增加 delist_date 过滤。
"""
from __future__ import annotations

import pandas as pd

from universe import get_universe as _get_universe_legacy


class UniverseData:
    """股票池 PIT Provider。

    as_of(t_date) -> DataFrame(code, name)（U0 语义）
    membership(code, t_date) -> "listed" | "not_yet" | "unknown"
    """

    def __init__(self, level: str = "U0"):
        self.level = level  # U0: 当前上市股重建（幸存者偏差已声明）

    def as_of(self, t_date: str) -> pd.DataFrame:
        """U0: 复用 universe.get_universe（list_date <= t + 当前名称非 ST）。"""
        return _get_universe_legacy(t_date)

    def membership(self, code: str, t_date: str) -> str:
        df = self.as_of(t_date)
        return "listed" if code in df["code"].values else "not_yet"

    @property
    def limitation(self) -> str:
        return (
            "U0: 当前上市股重建 — 无 delist master，存在幸存者偏差；"
            "历史 ST 状态非 Point-in-Time。U1+ 待数据源 spike。"
        )
