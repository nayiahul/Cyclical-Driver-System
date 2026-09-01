"""MarketData — 行情数据 PIT Provider。

契约: as_of(code, t) 返回 date <= t 的全部行情行；绝不返回未来数据。
加载: 复用 signals._load_price_data（内存缓存），as_of 内截断 + 断言。
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from pit.exceptions import FutureDataError, MissingDataError

# 可注入的原始加载器（测试 monkeypatch 点）
_raw_loader = None


def _default_loader(code: str) -> pd.DataFrame:
    from signals import _load_price_data

    return _load_price_data(code)


def _get_loader():
    return _raw_loader if _raw_loader is not None else _default_loader


class MarketData:
    """行情数据 PIT Provider。

    as_of(code, t_date) -> DataFrame(date<=t_date 的行)
        - 数据源含未来行（本地文件更新到 2026）→ **截断**返回 ≤t 行（as-of 视图核心语义）
        - 数据源最小日期 > t（如新股）→ 返回空（UNAVAILABLE）
    close_on_or_before(code, t_date) -> float | None（prior-known 白名单语义）
    effective_date(code, t_date) -> 实际最后可得日期
    has_future_data(code, t_date) -> bool（供审计：数据源是否含 >t 的行）

    注意: as_of 永不 raise（截断即正确）；HARD ERROR 由 PITGuard 层负责。
    """

    def __init__(self, loader=None):
        # loader 不在此绑定：调用时动态解析（支持测试 monkeypatch _raw_loader）
        self._loader = loader

    def _resolve_loader(self):
        return self._loader if self._loader is not None else _get_loader()

    def as_of(self, code: str, t_date: str) -> pd.DataFrame:
        """返回截至 t_date 的行情（闭区间，截断视图）。"""
        df = self._resolve_loader()(code)
        if df is None or len(df) == 0:
            return pd.DataFrame()

        t = pd.Timestamp(t_date)
        return df[df.index <= t].copy()

    def close_on_or_before(self, code: str, t_date: str) -> Optional[float]:
        """≤ t_date 的最近收盘价（执行价查询，prior-known fallback 白名单）。"""
        df = self.as_of(code, t_date)
        if df.empty or "close" not in df.columns:
            return None
        val = df["close"].iloc[-1]
        return float(val) if pd.notna(val) else None

    def effective_date(self, code: str, t_date: str) -> Optional[str]:
        """实际最后可得日期 (YYYY-MM-DD)。数据缺失返回 None。"""
        df = self.as_of(code, t_date)
        if df.empty:
            return None
        return str(df.index.max().date())

    def has_future_data(self, code: str, t_date: str) -> bool:
        """数据源是否含 > t_date 的行（供审计/guard，as_of 本身已截断）。"""
        df = self._loader(code)
        if df is None or len(df) == 0:
            return False
        return bool((df.index > pd.Timestamp(t_date)).any())

    def coverage(self, codes: list[str], t_date: str) -> dict[str, bool]:
        """{code: 是否有 ≤t_date 数据}（供 Coverage Audit）。"""
        out = {}
        for c in codes:
            try:
                df = self.as_of(c, t_date)
                out[c] = len(df) > 0
            except FutureDataError:
                out[c] = False
        return out
