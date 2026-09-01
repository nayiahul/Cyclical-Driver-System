"""PIT Contract v1 — 数据可信层统一入口。

用法:
    from pit import market, financial, universe, industry, guard

    mkt = market.MarketData()
    df = mkt.as_of("000001", "20220630")   # 绝不返回未来数据

依赖关系:
    raw adapters (CSV/TDX) → pit providers → domain logic (signals/screener/growth_os)
"""
from pit.market import MarketData
from pit.financial import FinancialData
from pit.universe import UniverseData
from pit.industry import IndustryData
from pit.guard import PITGuard
from pit.exceptions import PITViolation, FutureDataError, MissingDataError
from pit.contracts import DataPoint

__all__ = [
    "MarketData",
    "FinancialData",
    "UniverseData",
    "IndustryData",
    "PITGuard",
    "PITViolation",
    "FutureDataError",
    "MissingDataError",
    "DataPoint",
]
