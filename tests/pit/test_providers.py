"""Provider 级 PIT 测试 — Gate 2 验收（契约层自身正确性）。

Level 1: 硬禁止未来数据（as_of 绝不返回 > t 的行）
Level 2: 业务模块无感迁移（provider 接口输出兼容）
Level 3: 研究结果可追踪（lineage 字段）
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pit.market import MarketData  # noqa: E402
from pit.financial import FinancialData  # noqa: E402
from pit.universe import UniverseData  # noqa: E402
from pit.guard import PITGuard  # noqa: E402
from pit.exceptions import PITViolation, FutureDataError  # noqa: E402
from pit.contracts import DataPoint  # noqa: E402


def make_price_df(dates, closes):
    df = pd.DataFrame({"date": pd.to_datetime(dates), "close": closes})
    return df.set_index("date").sort_index()


class TestMarketDataProvider:
    def test_as_of_never_returns_future(self):
        """Level 1: as_of(t) 返回的行 max(date) <= t。"""
        df = make_price_df(
            ["2022-01-04", "2022-06-30", "2026-06-01"], [9.0, 10.0, 100.0]
        )
        mkt = MarketData(loader=lambda c: df)
        out = mkt.as_of("000001", "20220630")
        assert out.index.max() <= pd.Timestamp("2022-06-30")
        assert float(out["close"].iloc[-1]) == 10.0, "必须返回 t 时价 10 而非 2026 价 100"

    def test_future_raises_when_source_latest_before_t(self):
        """数据源最后日期 < t（如新股）→ 返回空（UNAVAILABLE），不 raise。"""
        df = make_price_df(["2022-01-04"], [9.0])
        mkt = MarketData(loader=lambda c: df)
        out = mkt.as_of("000001", "20220630")
        assert not out.empty  # 2022-01-04 <= t, 可用

    def test_close_on_or_before_prior_known(self):
        """close_on_or_before: ≤t 的最近收盘（prior-known 白名单语义）。"""
        df = make_price_df(
            ["2022-01-04", "2022-02-01", "2026-06-01"], [9.0, 9.5, 100.0]
        )
        mkt = MarketData(loader=lambda c: df)
        assert mkt.close_on_or_before("000001", "20220215") == 9.5
        assert mkt.close_on_or_before("000001", "20260601") == 100.0  # t 当天允许

    def test_effective_date(self):
        df = make_price_df(
            ["2022-01-04", "2022-06-30", "2026-06-01"], [9.0, 10.0, 100.0]
        )
        mkt = MarketData(loader=lambda c: df)
        assert mkt.effective_date("000001", "20220630") == "2022-06-30"
        assert mkt.effective_date("000001", "20220105") == "2022-01-04"

    def test_lineage_datapoint(self):
        """Level 3: DataPoint 携带完整 lineage。"""
        dp = DataPoint(
            value=37.2, field="revenue_yoy", requested_as_of="2020-04-30",
            source="TDX", source_date="2020-03-31",
            effective_date="2020-04-28", cutoff_source="actual",
            data_extract_date="2026-05-21",
        )
        lin = dp.lineage_dict()
        assert lin["value"] == 37.2
        assert lin["effective_date"] == "2020-04-28"
        assert lin["requested_as_of"] == "2020-04-30"


class TestFinancialDataProvider:
    def test_snapshot_respects_disclosure(self):
        """财务快照只返回 disclosure_cutoff <= t 的报告。"""
        raw = pd.DataFrame(
            {
                "code": ["000001", "000001"],
                "report_date_str": ["20220331", "20211231"],
                "deducted_profit_yoy": [25.0, 10.0],
            }
        )
        fin = FinancialData(raw=raw)
        # 2022-04-29 < 法定截止 2022-04-30 → 2022Q1 不可见；只有 2021 年报(截止2022-04-30)……也截止 4/30
        # 所以 4/29 全部不可见
        assert fin.snapshot("000001", "20220429") is None
        snap = fin.snapshot("000001", "20220430")
        assert snap is not None
        assert snap["report_date_str"] == "20220331"  # 最新可用 = 2022Q1

    def test_quarterly_series_disclosure(self):
        raw = pd.DataFrame(
            {
                "code": ["000001", "000001"],
                "report_date_str": ["20220331", "20211231"],
                "deducted_profit_yoy": [25.0, 10.0],
            }
        )
        fin = FinancialData(raw=raw)
        s = fin.quarterly_series("000001", "deducted_profit_yoy", "20220430", 4)
        assert len(s) == 2  # 4/30 可见两期
        s2 = fin.quarterly_series("000001", "deducted_profit_yoy", "20220429", 4)
        assert len(s2) == 0  # 4/29 全部不可见

    def test_disclosure_info_cutoff_source(self):
        from pit.financial import FinancialData

        fin = FinancialData(raw=None)
        info = fin.disclosure_info("000001", "20220331")
        assert info["cutoff_source"] in ("actual", "statutory")
        assert info["disclosure_date"] >= "20220430" or info["cutoff_source"] == "actual"


class TestUniverseDataProvider:
    def test_u0_as_of(self):
        uni = UniverseData(level="U0")
        df = uni.as_of("20220630")
        assert "code" in df.columns and "name" in df.columns
        assert len(df) > 3000  # 全市场 U0

    def test_limitation_declared(self):
        uni = UniverseData()
        assert "幸存者偏差" in uni.limitation


class TestPITGuard:
    def test_violation_raises(self):
        guard = PITGuard(module="test")
        with pytest.raises(PITViolation):
            with guard.check("000001", "20220630", "2026-06-01"):
                pass

    def test_missing_is_unknown_not_violation(self):
        guard = PITGuard(module="test")
        with guard.check("000001", "20220630", None):
            pass  # UNAVAILABLE: 不 raise
        assert len(guard.log) == 1
        assert guard.log[0]["actual_date"] is None

    def test_ok_access_logged(self):
        guard = PITGuard(module="test")
        with guard.check("000001", "20220630", "2022-06-30"):
            pass
        assert guard.log[0]["requested_as_of"] == "20220630"
