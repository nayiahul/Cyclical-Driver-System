"""PIT 数据契约定义 — 一切数据必须是 As-Of-T 可获得。

语义:
    as_of(t) = 截至 t 日收盘已公开、已可得的数据（闭区间，含 t 日）。

    observation_time: 信号计算时点（当前 = 调仓日前一交易日收盘）
    execution_time:   交易执行时点（当前 = 调仓日收盘）
    契约保证: observation_time 使用的所有数据 date <= observation_time。

硬不变量（违反 → FutureDataError，禁止 fallback）:
    market:     max(price.date)  <= t
    financial:  max(disclosure_cutoff) <= t
    universe:   list_date <= t 且 (delist_date is None or delist_date > t)
    industry:   静态快照（Phase 1 显式声明限制，不假装 PIT）

缺失语义（D5 决策）:
    future data        → HARD ERROR (FutureDataError)
    missing historical → UNAVAILABLE (MissingDataError 或 None, 模块级处理)
    fallback to future → FORBIDDEN
    prior-known fallback → 仅白名单语义（如 close_on_or_before 执行价查询）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DataPoint:
    """带完整 lineage 的数据点（D9 Data Lineage，审计/调试模式）。"""

    value: Any
    field: str
    requested_as_of: str
    source: str
    source_date: Optional[str] = None       # 报告期/数据日期
    effective_date: Optional[str] = None    # 披露日/可用日
    cutoff_source: Optional[str] = None     # actual | statutory
    data_extract_date: Optional[str] = None  # 数据文件提取日期（L10）
    meta: dict = field(default_factory=dict)

    def lineage_dict(self) -> dict:
        return {
            "value": self.value,
            "field": self.field,
            "requested_as_of": self.requested_as_of,
            "source": self.source,
            "source_date": self.source_date,
            "effective_date": self.effective_date,
            "cutoff_source": self.cutoff_source,
            "data_extract_date": self.data_extract_date,
        }
