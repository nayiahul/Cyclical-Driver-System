"""pytest 共享 fixture — 固定数据快照（不依赖网络）。

Gate 1 要求: 测试必须可复现。所有测试数据用构造样本或本地缓存，
不触发 akshare/网络调用。
"""
import os
import sys

import pandas as pd
import pytest

# 确保项目根目录在 sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def sample_price_df():
    """构造价格 DataFrame：index=date(YYYYMMDD), close 列。

    场景: t_date=2022-06-30 时价格为 10，本地最新价 100（2026）。
    任何 PIT 正确实现必须只见 10。
    """
    dates = pd.to_datetime(
        ["2022-01-04", "2022-03-01", "2022-06-30", "2023-01-03", "2026-06-01"]
    )
    closes = [9.0, 9.5, 10.0, 11.0, 100.0]
    df = pd.DataFrame({"date": dates.strftime("%Y%m%d"), "close": closes})
    return df


@pytest.fixture(scope="session")
def sample_fin_df():
    """构造财务 DataFrame: report_date_str + disclosure 相关列。

    场景: 报告期 2022-03-31，实际披露 2022-04-25（法定截止 2022-04-30）。
    as_of(2022-04-01) 不可见，as_of(2022-04-25) 可见。
    """
    df = pd.DataFrame(
        {
            "code": ["000001", "000001"],
            "report_date_str": ["20220331", "20211231"],
            "deducted_profit_yoy": [25.0, 10.0],
        }
    )
    return df


@pytest.fixture(scope="session")
def sample_universe_df():
    """构造 Universe: 上市/退市边界。"""
    df = pd.DataFrame(
        {
            "code": ["000001", "600001"],
            "name": ["测试A", "测试B"],
            "list_date": ["19910101", "20100101"],
            "delist_date": [None, "20201231"],  # 600001 于 2020 退市
        }
    )
    return df


@pytest.fixture(scope="session")
def trade_cal():
    """本地交易日历（缓存文件存在时）。"""
    from trade_calendar import get_trade_calendar

    cal = get_trade_calendar("20220101", "20251231")
    return cal["trade_date"].tolist()
