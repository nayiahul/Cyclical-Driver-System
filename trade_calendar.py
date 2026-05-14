"""交易日历与调仓日期"""

import os
from datetime import datetime

import akshare as ak
import pandas as pd

from config.params import TRADE_CALENDAR_CACHE


def get_trade_calendar(start: str, end: str) -> pd.DataFrame:
    """
    获取A股交易日历。

    Args:
        start: 起始日期 "YYYYMMDD"
        end: 结束日期 "YYYYMMDD"

    Returns:
        DataFrame with columns: trade_date (str YYYYMMDD)
    """
    if os.path.exists(TRADE_CALENDAR_CACHE):
        df = pd.read_csv(TRADE_CALENDAR_CACHE, dtype={"trade_date": str})
        df = df[(df["trade_date"] >= start) & (df["trade_date"] <= end)]
        if len(df) > 0:
            return df.reset_index(drop=True)

    try:
        df = ak.tool_trade_date_hist_sina()
    except Exception as e:
        print(f"获取交易日历失败: {e}")
        raise

    df.columns = ["trade_date"]
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y%m%d")
    df = df.sort_values("trade_date").reset_index(drop=True)
    df.to_csv(TRADE_CALENDAR_CACHE, index=False)

    return df[(df["trade_date"] >= start) & (df["trade_date"] <= end)].reset_index(drop=True)


def get_rebalance_dates(start: str, end: str) -> list[str]:
    """
    获取每月首个交易日列表（调仓日）。

    Args:
        start: 起始日期 "YYYYMMDD"
        end: 结束日期 "YYYYMMDD"

    Returns:
        list of date strings "YYYYMMDD"
    """
    cal = get_trade_calendar(start, end)
    cal["ym"] = cal["trade_date"].str[:6]
    first_days = cal.groupby("ym")["trade_date"].first()
    return first_days.tolist()


def get_t_date(rebalance_date: str) -> str:
    """
    获取调仓日的前一个交易日（月末确认日）。

    Args:
        rebalance_date: 调仓日期 "YYYYMMDD"

    Returns:
        前一个交易日 "YYYYMMDD"
    """
    cal = get_trade_calendar("20000101", rebalance_date)
    if len(cal) < 2:
        raise ValueError(f"日历中找不到 {rebalance_date} 之前的交易日")
    return cal["trade_date"].iloc[-2]
