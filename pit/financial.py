"""FinancialData — 财务数据 PIT Provider。

契约: as_of(code, t) 只返回 disclosure_cutoff <= t 的财报（复用 data_governance）。
Financial PIT policy 位于 data_governance.py（实际披露日历 → 法定截止日 fallback）。
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from data_governance import filter_available_reports, load_tdx_raw
from pit.exceptions import MissingDataError


class FinancialData:
    """财务数据 PIT Provider（TDX 缓存）。

    snapshot(code, t_date) -> 最新可用财报 dict | None
    quarterly_series(code, field, t_date, n) -> pd.Series(report_date_str -> value)
    disclosure_info(code, report_period) -> {disclosure_date, cutoff_source}
    """

    def __init__(self, raw=None):
        self._raw = raw if raw is not None else load_tdx_raw()
        self._avail_cache: dict[str, pd.DataFrame] = {}  # t_date → 已治理表

    def _available(self, t_date: str) -> pd.DataFrame:
        if t_date in self._avail_cache:
            return self._avail_cache[t_date]
        if self._raw is None:
            return pd.DataFrame()
        df = self._raw.copy()
        df["code"] = df["code"].astype(str).str.zfill(6)
        out = filter_available_reports(df, t_date)
        self._avail_cache[t_date] = out
        return out

    def snapshot(self, code: str, t_date: str) -> Optional[dict]:
        """截至 t_date 的最新财报快照（含 lineage 字段）。"""
        avail = self._available(t_date)
        if avail.empty:
            return None
        sub = avail[avail["code"] == code]
        if sub.empty:
            return None
        latest = sub.sort_values("report_date_str").iloc[-1]
        return latest.to_dict()

    def quarterly_series(
        self, code: str, field: str, t_date: str, n_quarters: int = 12
    ) -> pd.Series:
        """截至 t_date 的最近 n 期单字段序列（report_date_str 索引）。"""
        avail = self._available(t_date)
        if avail.empty:
            return pd.Series(dtype=float)
        sub = avail[avail["code"] == code].sort_values("report_date_str")
        if sub.empty or field not in sub.columns:
            return pd.Series(dtype=float)
        return (
            sub.tail(n_quarters)
            .set_index("report_date_str")[field]
            .astype(float)
        )

    def disclosure_info(self, code: str, report_period: str) -> Optional[dict]:
        """报告期对应的披露日信息（数据治理层查询）。"""
        from data_governance import _load_calendar

        cal = _load_calendar()
        key = (str(code).zfill(6), report_period)
        if cal and key in cal:
            return {
                "disclosure_date": cal[key],
                "cutoff_source": "actual",
            }
        from data_governance import get_disclosure_cutoff

        return {
            "disclosure_date": get_disclosure_cutoff(report_period),
            "cutoff_source": "statutory",
        }
