"""股票池获取与基础过滤"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import akshare as ak
import pandas as pd

from config.params import IPO_LOCK_DAYS, STOCK_LIST_CACHE
from loguru import logger
from trade_calendar import get_trade_calendar

# AKShare 1.18.60: stock_info_a_code_name() returns columns ["code", "name"] only.
# No list_date column is present. However, the individual exchange APIs
# (SZ, SH main/STAR, BJ) each include listing dates in their responses.
# _get_listing_dates uses those bulk endpoints (~4 calls) as the primary path.

_WORKERS = 5  # parallel workers for per-stock listing-date queries
_RETRIES = 3  # retry count for flaky API connections


def get_stock_list() -> pd.DataFrame:
    """
    获取全部A股基础信息。

    Returns:
        DataFrame with columns: code, name, list_date
    """
    if os.path.exists(STOCK_LIST_CACHE):
        return pd.read_csv(STOCK_LIST_CACHE, dtype={"code": str, "name": str, "list_date": str})

    df = ak.stock_info_a_code_name()
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["name"] = df["name"].astype(str)

    list_dates = _get_listing_dates(df["code"].tolist())
    df["list_date"] = df["code"].map(list_dates)
    df = df.dropna(subset=["list_date"])
    df["list_date"] = df["list_date"].astype(str)

    os.makedirs(os.path.dirname(STOCK_LIST_CACHE), exist_ok=True)
    df.to_csv(STOCK_LIST_CACHE, index=False)
    logger.info(f"股票池已缓存至 {STOCK_LIST_CACHE}，共 {len(df)} 只")
    return df


def _get_listing_dates(codes: list[str]) -> dict[str, str]:
    """Get listing date for each stock code. Try bulk methods first, fall back to per-stock.

    AKShare 1.18.60's stock_info_a_code_name() does not include a list_date column,
    but the individual exchange APIs (SZ, SH, BJ) each include listing dates in their
    responses. This function uses those exchange-specific APIs in bulk (~4 calls)
    before falling back to per-stock queries.
    """
    # Fast path: check if stock_info_a_code_name now includes a list_date column
    # (future AKShare versions may add it, making this function trivial).
    try:
        df = ak.stock_info_a_code_name()  # cached, so cheap to re-query
        if "list_date" in df.columns:
            date_map = {}
            for _, row in df.iterrows():
                code = str(row["code"]).zfill(6)
                ld = str(row.get("list_date", ""))
                if ld and ld != "nan":
                    date_map[code] = ld[:8]
            if date_map:
                return date_map
    except Exception:
        pass

    # Bulk method: query exchange-specific APIs that include listing dates.
    date_map: dict[str, str] = {}

    def _mmdd(date_val) -> str:
        """Normalize various date types to YYYYMMDD string."""
        if isinstance(date_val, str):
            return date_val.replace("-", "")[:8]
        if hasattr(date_val, "strftime"):
            return date_val.strftime("%Y%m%d")
        return str(date_val)[:8]

    try:
        # SZ (Shenzhen) - includes A股上市日期 as string "1991-04-03"
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
        # SH main board A shares - includes 上市日期 as datetime.date
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
        # SH STAR market (科创板) - same columns as main board
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
        # BJ (Beijing Stock Exchange) - includes 上市日期 as datetime.date
        df_bj = ak.stock_info_bj_name_code()
        if "上市日期" in df_bj.columns:
            for _, row in df_bj.iterrows():
                code = str(row["证券代码"]).zfill(6)
                ld = _mmdd(row["上市日期"])
                if ld and ld != "nan":
                    date_map[code] = ld
    except Exception:
        pass

    # If bulk APIs covered all requested codes, return immediately.
    missing = [c for c in codes if c not in date_map]
    if not missing:
        return date_map

    logger.warning(
        f"Bulk listing-date APIs returned partial coverage: "
        f"{len(date_map)}/{len(codes)} codes. Fetching remaining {len(missing)} "
        f"via per-stock queries (slow path)."
    )

    # Per-stock fallback for codes not covered by bulk APIs.
    # Thread pool with retries for flaky network connections.
    def _fetch_listing_date(code: str) -> tuple[str, str] | None:
        for attempt in range(_RETRIES):
            try:
                # Primary: East Money individual stock info (direct 上市时间 field)
                info = ak.stock_individual_info_em(symbol=code)
                row = info[info["item"] == "上市时间"]
                if not row.empty:
                    ld = str(row["value"].iloc[0])
                    if len(ld) >= 8:
                        return code, ld[:8]
            except Exception:
                pass
            try:
                # Fallback: monthly history, first row = listing date
                hist = ak.stock_zh_a_hist(
                    symbol=code, period="monthly",
                    start_date="19900101", end_date="20241231", adjust="qfq",
                )
                if len(hist) > 0:
                    raw = hist["日期"].iloc[0]
                    return code, str(raw).replace("-", "")
            except Exception:
                pass
            if attempt < _RETRIES - 1:
                time.sleep(1.5)
        return None

    if missing:
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            futures = {pool.submit(_fetch_listing_date, code): code for code in missing}
            for fut in as_completed(futures):
                result = fut.result()
                if result is not None:
                    code, ld = result
                    date_map[code] = ld

    return date_map


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
        return not_st.head(0)

    lock_idx = max(0, t_idx - IPO_LOCK_DAYS)
    lock_date = cal_dates[lock_idx]
    filtered = not_st[not_st["list_date"] <= lock_date]
    removed_ipo = len(not_st) - len(filtered)

    logger.info(
        f"universe @ {trade_date}: {len(filtered)} stocks "
        f"(removed: {removed_not_listed} unlisted, "
        f"{removed_st} ST, {removed_ipo} IPO-locked)"
    )
    return filtered[["code", "name"]].reset_index(drop=True)
