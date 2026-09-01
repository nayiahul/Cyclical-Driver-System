"""PIT 异常类型。

FutureDataError: 请求 as_of(t)，数据源返回日期 > t（未来数据）→ HARD ERROR
MissingDataError: 历史数据不存在 → UNAVAILABLE（模块级策略处理，不 crash 全链）
"""
from __future__ import annotations


class PITViolation(Exception):
    """PIT 契约违反：未来数据被访问。"""

    def __init__(self, what: str, requested_as_of: str, actual_date: str):
        self.what = what
        self.requested_as_of = requested_as_of
        self.actual_date = actual_date
        super().__init__(
            f"PIT 违规: {what} 请求 as_of={requested_as_of} "
            f"但实际数据日期={actual_date} (未来数据禁止访问)"
        )


class FutureDataError(PITViolation):
    """未来数据访问（HARD ERROR，必须 raise）。"""


class MissingDataError(Exception):
    """历史数据缺失（UNAVAILABLE，模块级 quarantine/skip）。"""

    def __init__(self, what: str, as_of: str, reason: str = ""):
        self.what = what
        self.as_of = as_of
        super().__init__(f"数据缺失: {what} @ {as_of} {reason}")
