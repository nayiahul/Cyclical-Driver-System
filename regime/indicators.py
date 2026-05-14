"""5维度市场周期指标计算"""
import os

import akshare as ak
import numpy as np
import pandas as pd
from loguru import logger

from trade_calendar import get_trade_calendar

INDEX_CACHE = "data/cache/index_399300.csv"
PE_CACHE = "data/cache/market_pe.csv"
MARGIN_CACHE = "data/cache/margin_data.csv"


def _load_index_data() -> pd.DataFrame:
    """加载沪深300日线，缓存到CSV"""
    if os.path.exists(INDEX_CACHE):
        df = pd.read_csv(INDEX_CACHE, dtype={"date": str})
        df["date"] = pd.to_datetime(df["date"])
        return df

    raw = ak.stock_zh_index_daily(symbol="sz399300")
    df = raw[["date", "close"]].copy()
    df["close"] = df["close"].astype(float)
    os.makedirs(os.path.dirname(INDEX_CACHE), exist_ok=True)
    df.to_csv(INDEX_CACHE, index=False)
    logger.info(f"沪深300日线已缓存: {len(df)} 条")
    return df


def index_trend(trade_dates: list[str]) -> pd.DataFrame:
    """
    计算沪深300趋势指标。

    Returns:
        DataFrame index=YYYYMM, columns=[close, ma60, ma120, ma200,
        above_ma200, ma60_gt_ma120]
    """
    df = _load_index_data()
    df = df.set_index("date").sort_index()
    df["ma60"] = df["close"].rolling(60).mean()
    df["ma120"] = df["close"].rolling(120).mean()
    df["ma200"] = df["close"].rolling(200).mean()

    trade_idx = pd.to_datetime(trade_dates, format="%Y%m%d")
    aligned = df.reindex(trade_idx, method="ffill")

    result = pd.DataFrame({
        "close": aligned["close"].values,
        "ma60": aligned["ma60"].values,
        "ma120": aligned["ma120"].values,
        "ma200": aligned["ma200"].values,
        "above_ma200": (aligned["close"] > aligned["ma200"]).values,
        "ma60_gt_ma120": (aligned["ma60"] > aligned["ma120"]).values,
    }, index=[d[:6] for d in trade_dates])
    return result


def market_breadth(trade_dates: list[str]) -> pd.DataFrame:
    """
    市场广度代理：指数收盘价 > MA20 的交易日占比（过去60日）。

    Returns:
        DataFrame index=YYYYMM, columns=[breadth_ratio]
    """
    df = _load_index_data()
    df = df.set_index("date").sort_index()
    df["ma20"] = df["close"].rolling(20).mean()
    df["above_ma20"] = (df["close"] > df["ma20"]).astype(int)
    df["breadth_ratio"] = df["above_ma20"].rolling(60).mean()

    trade_idx = pd.to_datetime(trade_dates, format="%Y%m%d")
    aligned = df.reindex(trade_idx, method="ffill")

    result = pd.DataFrame({
        "breadth_ratio": aligned["breadth_ratio"].values,
    }, index=[d[:6] for d in trade_dates])
    return result


def new_high_ratio(trade_dates: list[str]) -> pd.DataFrame:
    """
    创新高比例代理：指数距52周（250日）高点的距离。

    距离 < 5% → 视为创新高状态
    距离 > 15% → 视为远离新高

    Returns:
        DataFrame index=YYYYMM, columns=[dist_from_high]
    """
    df = _load_index_data()
    df = df.set_index("date").sort_index()
    df["high_250"] = df["close"].rolling(250).max()
    df["dist_from_high"] = (df["high_250"] - df["close"]) / df["high_250"]

    trade_idx = pd.to_datetime(trade_dates, format="%Y%m%d")
    aligned = df.reindex(trade_idx, method="ffill")

    result = pd.DataFrame({
        "dist_from_high": aligned["dist_from_high"].values,
    }, index=[d[:6] for d in trade_dates])
    return result


def risk_appetite(trade_dates: list[str]) -> pd.DataFrame:
    """
    风险偏好代理：全市场PE的60日变化率。

    Returns:
        DataFrame index=YYYYMM, columns=[pe_60d_change]
    """
    if os.path.exists(PE_CACHE):
        pe_df = pd.read_csv(PE_CACHE, dtype={"日期": str})
    else:
        raw = ak.stock_market_pe_lg(symbol="上证A股")
        pe_df = raw[["日期", "市盈率"]].copy()
        pe_df.columns = ["date", "pe"]
        pe_df["pe"] = pe_df["pe"].astype(float)
        os.makedirs(os.path.dirname(PE_CACHE), exist_ok=True)
        pe_df.to_csv(PE_CACHE, index=False)

    pe_df["date"] = pd.to_datetime(pe_df["date"])
    pe_df = pe_df.set_index("date").sort_index()
    pe_df["pe_60d_change"] = pe_df["pe"].pct_change(60)

    trade_idx = pd.to_datetime(trade_dates, format="%Y%m%d")
    aligned = pe_df.reindex(trade_idx, method="ffill")

    result = pd.DataFrame({
        "pe_60d_change": aligned["pe_60d_change"].values,
    }, index=[d[:6] for d in trade_dates])
    return result


def liquidity(trade_dates: list[str]) -> pd.DataFrame:
    """
    流动性指标：两市融资余额合计的周环比变化。

    Returns:
        DataFrame index=YYYYMM, columns=[margin_weekly_change, flow_3week]
    """
    if os.path.exists(MARGIN_CACHE):
        margin_df = pd.read_csv(MARGIN_CACHE, dtype={"日期": str})
    else:
        sh = ak.macro_china_market_margin_sh()
        sz = ak.macro_china_market_margin_sz()
        sh_df = sh[["日期", "融资融券余额"]].copy()
        sh_df.columns = ["date", "balance_sh"]
        sz_df = sz[["日期", "融资融券余额"]].copy()
        sz_df.columns = ["date", "balance_sz"]
        margin_df = pd.merge(sh_df, sz_df, on="date", how="inner")
        margin_df["total_balance"] = (
            margin_df["balance_sh"].astype(float) + margin_df["balance_sz"].astype(float)
        )
        os.makedirs(os.path.dirname(MARGIN_CACHE), exist_ok=True)
        margin_df.to_csv(MARGIN_CACHE, index=False)

    margin_df["date"] = pd.to_datetime(margin_df["date"])
    margin_df = margin_df.set_index("date").sort_index()
    margin_df["weekly_change"] = margin_df["total_balance"].pct_change(5)
    margin_df["flow_sign"] = np.sign(margin_df["weekly_change"])
    margin_df["flow_3week"] = margin_df["flow_sign"].rolling(3).sum()

    trade_idx = pd.to_datetime(trade_dates, format="%Y%m%d")
    aligned = margin_df.reindex(trade_idx, method="ffill")

    result = pd.DataFrame({
        "margin_weekly_change": aligned["weekly_change"].values,
        "flow_3week": aligned["flow_3week"].values,
    }, index=[d[:6] for d in trade_dates])
    return result
