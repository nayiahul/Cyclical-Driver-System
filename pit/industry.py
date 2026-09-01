"""IndustryData — 行业映射 PIT Provider。

Phase 1: 静态快照（sw_stock_industry.csv 为 2026-05 单时点），显式声明限制，不假装 PIT。
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


class IndustryData:
    """行业映射 Provider（U0: 静态快照 + limitation 标记）。"""

    def __init__(self, path: str = "data/cache/sw_stock_industry.csv"):
        self._df = pd.read_csv(path, dtype={"code": str})
        self._map = dict(zip(self._df["code"], self._df["sw1"]))
        self._snapshot_date = "2026-05"  # 数据清单: 2026-05 快照

    def as_of(self, code: str, t_date: str) -> Optional[str]:
        """返回行业（静态快照；不假装按 t_date 变化）。"""
        return self._map.get(code)

    def snapshot_date(self) -> str:
        return self._snapshot_date

    @property
    def limitation(self) -> str:
        return (
            f"行业映射为 {self._snapshot_date} 单时点快照，"
            "历史行业分类可能不准确（申万每年调整 1-2 次）；"
            "建议回测结论有效窗口限制在 3 年内。"
        )
