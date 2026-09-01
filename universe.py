"""股票池获取与基础过滤"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import akshare as ak
import pandas as pd
from loguru import logger

from config.params import IPO_LOCK_DAYS, STOCK_LIST_CACHE
from trade_calendar import get_trade_calendar

_WORKERS = 5
_RETRIES = 3
_FAR_FUTURE = "20991231"


def get_stock_list() -> pd.DataFrame:
    """
    获取全部A股基础信息。

    Returns:
        DataFrame with columns: code, name, list_date
    """
    if os.path.exists(STOCK_LIST_CACHE):
        try:
            df = pd.read_csv(STOCK_LIST_CACHE, dtype={"code": str, "name": str, "list_date": str})
            if len(df) > 0:
                return df
        except Exception:
            logger.warning(f"缓存文件 {STOCK_LIST_CACHE} 损坏，重新获取")

    df = ak.stock_info_a_code_name()
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["name"] = df["name"].astype(str)

    list_dates = _get_listing_dates(df["code"].tolist())
    df["list_date"] = df["code"].map(list_dates)
    missing_before = len(df)
    df = df.dropna(subset=["list_date"])
    missing_after = len(df)
    if missing_before > missing_after:
        logger.warning(f"{missing_before - missing_after} 只股票无上市日期，已剔除")
    df["list_date"] = df["list_date"].astype(str)

    os.makedirs(os.path.dirname(STOCK_LIST_CACHE), exist_ok=True)
    df.to_csv(STOCK_LIST_CACHE, index=False)
    logger.info(f"股票池已缓存至 {STOCK_LIST_CACHE}，共 {len(df)} 只")
    return df


def _get_listing_dates(codes: list[str]) -> dict[str, str]:
    """Get listing date for each stock code. Try bulk exchange APIs first, per-stock fallback."""

    def _mmdd(date_val) -> str:
        """Normalize various date types to YYYYMMDD string."""
        if date_val is None or (isinstance(date_val, float) and pd.isna(date_val)):
            return ""
        if isinstance(date_val, str):
            return date_val.replace("-", "")[:8]
        if hasattr(date_val, "strftime"):
            return date_val.strftime("%Y%m%d")
        return str(date_val)[:8]

    date_map: dict[str, str] = {}

    try:
        df_sz = ak.stock_info_sz_name_code(symbol="A股列表")
        if "A股上市日期" in df_sz.columns:
            for _, row in df_sz.iterrows():
                code = str(row["A股代码"]).zfill(6)
                ld = _mmdd(row.get("A股上市日期", ""))
                if ld and ld != "nan":
                    date_map[code] = ld
    except Exception:
        pass

    try:
        df_sh = ak.stock_info_sh_name_code(symbol="主板A股")
        if "上市日期" in df_sh.columns:
            for _, row in df_sh.iterrows():
                code = str(row["证券代码"]).zfill(6)
                ld = _mmdd(row["上市日期"])
                if ld and ld != "nan":
                    date_map[code] = ld
    except Exception:
        pass

    try:
        df_kcb = ak.stock_info_sh_name_code(symbol="科创板")
        if "上市日期" in df_kcb.columns:
            for _, row in df_kcb.iterrows():
                code = str(row["证券代码"]).zfill(6)
                ld = _mmdd(row["上市日期"])
                if ld and ld != "nan":
                    date_map[code] = ld
    except Exception:
        pass

    try:
        df_bj = ak.stock_info_bj_name_code()
        if "上市日期" in df_bj.columns:
            for _, row in df_bj.iterrows():
                code = str(row["证券代码"]).zfill(6)
                ld = _mmdd(row["上市日期"])
                if ld and ld != "nan":
                    date_map[code] = ld
    except Exception:
        pass

    missing = [c for c in codes if c not in date_map]
    if not missing:
        return date_map

    logger.warning(
        f"Bulk listing-date APIs returned partial coverage: "
        f"{len(date_map)}/{len(codes)} codes. Fetching remaining {len(missing)} "
        f"via per-stock queries (slow path)."
    )

    def _fetch_listing_date(code: str) -> tuple[str, str] | None:
        for attempt in range(_RETRIES):
            try:
                info = ak.stock_individual_info_em(symbol=code)
                row = info[info["item"] == "上市时间"]
                if not row.empty:
                    ld = str(row["value"].iloc[0])
                    if len(ld) >= 8:
                        return code, ld[:8]
            except Exception:
                pass
            try:
                hist = ak.stock_zh_a_hist(
                    symbol=code, period="monthly",
                    start_date="19900101", end_date=_FAR_FUTURE, adjust="qfq",
                )
                if len(hist) > 0:
                    raw = hist["日期"].iloc[0]
                    return code, str(raw).replace("-", "")
            except Exception:
                pass
            if attempt < _RETRIES - 1:
                time.sleep(1.5)
        return None

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = {pool.submit(_fetch_listing_date, code): code for code in missing}
        for fut in as_completed(futures):
            result = fut.result()
            if result is not None:
                code, ld = result
                date_map[code] = ld

    return date_map


_UNIVERSE_CACHE: dict[str, pd.DataFrame] = {}  # Gate 0-A: 按 t_date 缓存（无语义变更）


def get_universe(trade_date: str) -> pd.DataFrame:
    """
    获取指定交易日的可交易股票池。

    过滤条件：
    1. 已上市 (list_date <= trade_date)
    2. 非ST (名称不含 ST、*ST)
    3. 非新股首月 (list_date 早于 trade_date 至少 IPO_LOCK_DAYS=20 个交易日)

    Args:
        trade_date: 交易日期 "YYYYMMDD"

    Returns:
        DataFrame with columns: code, name
    """
    if trade_date in _UNIVERSE_CACHE:
        return _UNIVERSE_CACHE[trade_date].copy()

    stocks = get_stock_list()
    total = len(stocks)

    listed = stocks[stocks["list_date"] <= trade_date]
    removed_not_listed = total - len(listed)

    not_st = listed[~listed["name"].str.contains(r"\*?ST", na=False)]
    removed_st = len(listed) - len(not_st)

    cal = get_trade_calendar("19900101", trade_date)
    cal_dates = cal["trade_date"].tolist()
    try:
        t_idx = cal_dates.index(trade_date)
    except ValueError:
        logger.warning(f"{trade_date} 非交易日，返回空 universe")
        return not_st.iloc[:0]

    lock_idx = max(0, t_idx - IPO_LOCK_DAYS)
    lock_date = cal_dates[lock_idx]
    filtered = not_st[not_st["list_date"] <= lock_date]
    removed_ipo = len(not_st) - len(filtered)

    logger.info(
        f"universe @ {trade_date}: {len(filtered)} stocks "
        f"(removed: {removed_not_listed} unlisted, "
        f"{removed_st} ST, {removed_ipo} IPO-locked)"
    )
    result = filtered[["code", "name"]].reset_index(drop=True)
    _UNIVERSE_CACHE[trade_date] = result
    return result.copy()
