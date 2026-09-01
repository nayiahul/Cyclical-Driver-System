"""PITGuard — 未来数据防火墙。

用法:
    with PITGuard(module="screener"):
        ... 业务计算 ...

记录: (module, code, requested_as_of, actual_effective_date)
任意 actual > requested → PITViolation (HARD ERROR)
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Optional

from pit.exceptions import PITViolation


class PITGuard:
    """上下文管理器：记录并强制 requested >= actual。"""

    def __init__(self, module: str, log: Optional[list] = None):
        self.module = module
        self.log = log if log is not None else []
        self.violations: list[PITViolation] = []

    @contextmanager
    def check(self, code: str, requested_as_of: str, actual_date: Optional[str]):
        """记录一次数据访问；actual > requested 时 raise。

        actual_date 为 None（数据缺失）→ 记录 UNKNOWN，不 raise（UNAVAILABLE 语义）。
        """
        entry = {
            "module": self.module,
            "code": code,
            "requested_as_of": requested_as_of,
            "actual_date": actual_date,
        }
        try:
            yield entry
        finally:
            self.log.append(entry)
            if actual_date is not None and actual_date > requested_as_of:
                viol = PITViolation(
                    f"{self.module}:{code}", requested_as_of, actual_date
                )
                self.violations.append(viol)
                raise viol

    def report(self) -> dict:
        return {
            "module": self.module,
            "accesses": len(self.log),
            "violations": [str(v) for v in self.violations],
        }
