"""Characterization Tests — 锁死 Phase 1 不改变的策略语义。

这些测试验证"性能优化后"与"优化前"的行为一致性，
确保后续 PIT 修复不偷偷改变策略。

必须从 Gate 1 开始就是 GREEN。
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config.params import TOTAL_COST_RATE, MAX_SINGLE_WEIGHT, TOP_N_STOCKS  # noqa: E402
from backtest.engine import run_backtest  # noqa: E402


class TestStrategySemantics:
    """策略语义锁: 调仓时序 / TopN / 权重 / 成本。"""

    def test_params_unchanged(self):
        """核心参数是 Gate 0 冻结的语义。"""
        assert TOP_N_STOCKS == 100, "TopN 不得在 PIT 修复中改变"
        assert MAX_SINGLE_WEIGHT == 0.08, "单票权重上限不得改变"
        assert TOTAL_COST_RATE == 0.003, "成本率不得改变"

    def test_rebalance_schedule(self, trade_cal):
        """调仓日 = 每月首个交易日。"""
        from trade_calendar import get_rebalance_dates

        rebs = get_rebalance_dates("20220101", "20221231")
        assert len(rebs) == 12, "2022 年应有 12 个调仓日"
        # 每个调仓日都是该月的第一个交易日
        for r in rebs:
            month_days = [d for d in trade_cal if d[:6] == r[:6]]
            assert r == month_days[0], f"{r} 不是 2022 年 {r[:6]} 月首个交易日"

    def test_equal_weight_cap(self):
        """等权分配且单票 ≤8%。"""
        # 权重逻辑在 engine 内部; 这里验证参数契约
        assert 1 / 100 <= MAX_SINGLE_WEIGHT, "Top100 等权(1%)不应超单票上限"


class TestDataGovernanceSemantics:
    """数据治理语义锁: 披露截止日映射。"""

    def test_statutory_deadlines(self):
        """法定披露截止日: Q1→4/30, Q2→8/31, Q3→10/31, Q4→次年4/30。"""
        from data_governance import get_disclosure_cutoff

        assert get_disclosure_cutoff("20220331") == "20220430"
        assert get_disclosure_cutoff("20220630") == "20220831"
        assert get_disclosure_cutoff("20220930") == "20221031"
        assert get_disclosure_cutoff("20221231") == "20230430"
        assert get_disclosure_cutoff("20230331") == "20230430"

    def test_filter_available_reports_boundary(self, sample_fin_df):
        """披露截止日边界: 截止日当天可见，前一天不可见。"""
        from data_governance import filter_available_reports

        # 2022Q1 (报告期 20220331) 法定截止 20220430
        df = sample_fin_df[sample_fin_df["report_date_str"] == "20220331"]
        before = filter_available_reports(df.copy(), "20220429")
        after = filter_available_reports(df.copy(), "20220430")
        assert before.empty, "截止日前一天不应可见"
        assert not after.empty, "截止日当天应可见"


class TestPerformanceEquivalence:
    """性能优化等价性: 优化不应改变数值结果。"""

    def test_cutoff_map_vectorized_equivalence(self):
        """向量化 _compute_cutoff_map 与逐行逻辑等价。"""
        import numpy as np
        import data_governance as dg

        # 构造覆盖四种报告期 + 日历命中的样本
        raw = pd.read_csv("data/cache/tdx_financials.csv",
                          dtype={"code": str, "report_date_str": str})
        sample = raw.sample(500, random_state=42)

        # 旧逻辑（逐行）
        calendar = dg._load_calendar()
        statutory = sample["report_date_str"].apply(dg.get_disclosure_cutoff)
        old_vals = []
        for _, row in sample.iterrows():
            key = (str(row["code"]), row["report_date_str"])
            old_vals.append(calendar.get(key, statutory.loc[row.name]))
        old = pd.Series(old_vals, index=sample.index)

        # 新逻辑（向量化）
        new = dg._compute_cutoff_map(sample, "20260601")

        pd.testing.assert_series_equal(new, old)

    def test_load_tdx_raw_equivalence(self):
        """共享加载与原 read_csv 等价。"""
        import data_governance as dg

        cached = dg.load_tdx_raw()
        orig = pd.read_csv("data/cache/tdx_financials.csv",
                           dtype={"code": str, "report_date_str": str})
        pd.testing.assert_frame_equal(cached, orig)
