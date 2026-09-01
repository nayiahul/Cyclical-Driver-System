"""PIT Remediation Tests — 当前代码下应 RED（复现泄漏），PIT 修复后转 GREEN。

对应 PDR P0-1/P0-2/P0-3:
- T-MKT-01: 市场数据未来函数（iloc[-1] 无 t_date 截断）
- T-MKT-02: 行业动量未来函数
- T-FIN-01: 财务披露日前视
- T-UNI-01: Universe 非 PIT（退市股/历史 ST）
- T-GRD-01: No-Future-Access Guard（回测记录 requested vs actual）
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import screener  # noqa: E402
import signals  # noqa: E402
from data_governance import filter_available_reports  # noqa: E402


def make_price_df(t_prices: dict, future_prices: dict, p60_price: float = 9.5):
    """构造 ≥200 行价格数据（datetime index, close 列）。

    时间结构:
      2021-01 ~ 60日前(2022-04附近) : p60_price (9.5)
      60日前 ~ t_date(2022-06-30)   : t_prices[code]  (t 时真实价)
      2026-06-01                    : future_prices[code]  (未来价, 泄漏源)

    正确实现 ret = t价/9.5 - 1；泄漏实现 ret = 未来价/9.5 - 1。
    """
    from trade_calendar import get_trade_calendar

    cal = get_trade_calendar("20210101", "20220630")
    dates = cal["trade_date"].tolist()
    # 60 日前截点（t_date=20220630 时约 2022-04-06）
    cut = dates[-61] if len(dates) > 61 else dates[0]
    rows = []
    for d in dates:
        px = p60_price if d <= cut else t_prices
        rows.append((pd.Timestamp(d), px))
    # 未来泄漏价
    rows.append((pd.Timestamp("2026-06-01"), future_prices))
    df = pd.DataFrame(rows, columns=["date", "close"]).set_index("date").sort_index()
    return df


def make_prices(t_prices: dict, future_prices: dict):
    """为 5 只股票构造价格 dict: {code: price_df}。"""
    return {c: make_price_df(t_prices, future_prices) for c in t_prices}


# 5 只同行业股票: t 时价格 9.0~11.0 (正确排序 A<E), 未来价 A 最高 (泄漏排序 A>E)
CODES = ["A", "B", "C", "D", "E"]
T_PRICES = {"A": 9.0, "B": 9.5, "C": 10.0, "D": 10.5, "E": 11.0}
FUTURE = {"A": 100.0, "B": 50.0, "C": 25.0, "D": 12.0, "E": 6.0}
IND_MAP = {c: "电子" for c in CODES}


# ---------- T-MKT-01: RPS60 未来函数 ----------
class TestMarketPIT:
    def test_rps60_no_future_price(self, monkeypatch):
        """RPS60 不得使用 t_date 之后的收盘价。

        正确: ret = t价/60日前价 → A(-5.3%) < E(+15.8%) → 分位 A < E
        泄漏: ret = 未来价/60日前价 → A(+953%) > E(-37%) → 分位 A > E
        """
        monkeypatch.setattr(
            screener, "_load_price_data", lambda c: make_price_df(T_PRICES[c], FUTURE[c])
        )
        rps = screener.compute_rps60(CODES, "20220630", IND_MAP)
        assert len(rps) == 5, f"RPS 应覆盖 5 只股票, 实际 {len(rps)}"
        assert rps["A"] < rps["E"], (
            f"RPS60 使用了未来价格! A={rps['A']} >= E={rps['E']} "
            "(正确排序应 A<E; 若 A>=E 则 iloc[-1] 泄漏到 2026 价)"
        )

    def test_industry_momentum_no_future(self, monkeypatch):
        """行业动量不得使用未来价格。"""
        monkeypatch.setattr(
            screener, "_load_price_data", lambda c: make_price_df(T_PRICES[c], FUTURE[c])
        )
        mom = screener.compute_industry_momentum(CODES, "20220630", IND_MAP)
        assert "A" in mom
        # 正确: 行业 median(5.3%) < 1.0; 泄漏: median(+163%) > 1.0
        assert abs(mom["A"]) < 1.0, (
            f"行业动量异常 ({mom['A']:.2%}) → 使用了 2026 未来价"
        )


# ---------- T-FIN-01: 财务披露日前视 ----------
class TestFinancialPIT:
    def test_disclosure_cutoff(self):
        """报告期 2022-03-31（无实际披露日历 → 法定截止 2022-04-30）:

        - as_of(2022-04-29) → 不可见（截止日前）
        - as_of(2022-04-30) → 可见
        """
        df = pd.DataFrame(
            {"code": ["000001"], "report_date_str": ["20220331"],
             "deducted_profit_yoy": [25.0]}
        )
        before = filter_available_reports(df.copy(), "20220429")
        assert before.empty, "法定截止日前不应可见 2022Q1 财报 (2022-04-29)"

        after = filter_available_reports(df.copy(), "20220430")
        assert not after.empty, "法定截止日当天应可见 2022Q1 财报 (2022-04-30)"

    def test_s1_respects_disclosure(self, monkeypatch):
        """S1 必须通过 filter_available_reports 获取财务数据。

        monkeypatch 必须打在 signals 命名空间（signals.load_tdx_raw），
        因为 compute_S1 内引用的是 import 进 signals 的绑定。
        """
        df = pd.DataFrame(
            {"code": ["000001"], "report_date_str": ["20220331"],
             "deducted_profit_yoy": [25.0], "deducted_profit_q": [1e8],
             "operating_cash_flow": [1e8], "revenue_yoy": [10.0]}
        )
        monkeypatch.setattr(signals, "load_tdx_raw", lambda: df.copy())
        # t_date 2022-04-01 < 披露截止 2022-04-30 → S1 应无数据
        s1 = signals.compute_S1("20220401", ["000001"], {"000001": "电子"})
        assert len(s1) == 0, "S1 在披露截止日前不应看到 2022Q1 财报 (2022-04-01)"


# ---------- T-UNI-01: Universe 非 PIT ----------
class TestUniversePIT:
    def test_delisted_excluded(self):
        """退市股在退市日后不得出现在 Universe（U1 未实现，预期 xfail）。"""
        pytest.xfail("Universe PIT U1 未实现（缺 delist master, 数据源 spike 待定）")

    def test_historical_st(self):
        """历史 ST 状态必须是 Point-in-Time（U2 未实现，预期 xfail）。"""
        pytest.xfail("历史 ST 状态未实现（U2）")


# ---------- T-GRD-01: No-Future-Access Guard ----------
class TestFutureGuard:
    def test_backtest_audit_no_future(self):
        """回测审计日志 requested_as_of >= actual_effective_date（Gate 6 全量）。"""
        pytest.skip("集成测试在 Gate 6: 全量回测 + audit 日志校验")
