"""交易日历与调仓日期"""

import os

import akshare as ak
import pandas as pd
from loguru import logger

from config.params import TRADE_CALENDAR_CACHE

_CALENDAR_EPOCH = "19901219"


_CAL_FULL: pd.DataFrame | None = None  # Gate 0-A: 全表缓存（无语义变更）


def get_trade_calendar(start: str, end: str) -> pd.DataFrame:
    """
    获取A股交易日历。

    Args:
        start: 起始日期 "YYYYMMDD"
        end: 结束日期 "YYYYMMDD"

    Returns:
        DataFrame with columns: trade_date (str YYYYMMDD)
    """
    global _CAL_FULL
    if _CAL_FULL is None:
        if os.path.exists(TRADE_CALENDAR_CACHE):
            _CAL_FULL = pd.read_csv(TRADE_CALENDAR_CACHE, dtype={"trade_date": str})

    if _CAL_FULL is not None:
        cached = _CAL_FULL[(_CAL_FULL["trade_date"] >= start) & (_CAL_FULL["trade_date"] <= end)]
        if len(cached) > 0:
            # 验证缓存覆盖范围：若缓存结束日期早于请求结束日期，可能过期
            if cached["trade_date"].iloc[-1] < end:
                logger.warning(f"缓存可能过期: 请求结束于 {end} 但缓存截止于 {cached['trade_date'].iloc[-1]}，重新获取")
            else:
                return cached.reset_index(drop=True)

    try:
        df = ak.tool_trade_date_hist_sina()
    except Exception:
        logger.error("获取交易日历失败")
        raise

    if df.empty:
        raise RuntimeError("AKShare 返回空的交易日历数据，请检查网络或 API 状态")

    df.columns = ["trade_date"]
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y%m%d")
    df = df.sort_values("trade_date").reset_index(drop=True)
    os.makedirs(os.path.dirname(TRADE_CALENDAR_CACHE), exist_ok=True)
    df.to_csv(TRADE_CALENDAR_CACHE, index=False)
    logger.info(f"交易日历已缓存至 {TRADE_CALENDAR_CACHE}，共 {len(df)} 条")
    _CAL_FULL = df

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

    前置条件: rebalance_date 必须是交易日（由 get_rebalance_dates 返回的日期天然满足）。

    Args:
        rebalance_date: 调仓日期 "YYYYMMDD"

    Returns:
        前一个交易日 "YYYYMMDD"
    """
    cal = get_trade_calendar(_CALENDAR_EPOCH, rebalance_date)
    if len(cal) < 2:
        raise ValueError(f"日历中找不到 {rebalance_date} 之前的交易日")
    return cal["trade_date"].iloc[-2]
