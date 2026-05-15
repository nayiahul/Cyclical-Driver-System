"""Alpha信号计算：S3(动量) S4(行业共振) S5(盈利稳定性) S7(现金流质量)"""
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import akshare as ak
import numpy as np
import pandas as pd
from loguru import logger

from config.params import (
    FIN_START_YEAR, MOMENTUM_DAYS_ABOVE_MA, ROE_MIN_QUARTERS,
    RPS60_MIN, SECTOR_BREADTH_MIN, SECTOR_TOP_PCT,
)
from industry import get_sw_industry
from trade_calendar import get_trade_calendar

FIN_CACHE = "data/cache/financial_data.csv"
_PRICE_MEM_CACHE: dict[str, pd.DataFrame] = {}


def _load_price_data(code: str) -> pd.DataFrame:
    """Load cached daily OHLCV data for a stock (memory + disk cache)."""
    if code in _PRICE_MEM_CACHE:
        return _PRICE_MEM_CACHE[code]
    path = f"data/cache/daily_prices/{code}.csv"
    if os.path.exists(path):
        df = pd.read_csv(path, dtype={"date": str})
        df["date"] = pd.to_datetime(df["date"])
        result = df.set_index("date").sort_index()
    else:
        result = pd.DataFrame()
    _PRICE_MEM_CACHE[code] = result
    return result


def _zscore(series: pd.Series) -> pd.Series:
    """Z-Score with 1%/99% winsorization."""
    lo, hi = series.quantile(0.01), series.quantile(0.99)
    clipped = series.clip(lo, hi)
    mu, sigma = clipped.mean(), clipped.std()
    if sigma == 0 or pd.isna(sigma):
        return pd.Series(0.0, index=series.index)
    return (clipped - mu) / sigma


def compute_S3(t_date: str, codes: list[str], industry_map: dict[str, str]) -> pd.Series:
    """
    S3 个股动量。5项条件全部满足 → RPS60的行业内Z-Score；否则NaN。

    Conditions:
    1. RPS60 >= 65 (intra-industry percentile)
    2. close > MA50
    3. MA50 > MA200
    4. 30-day amplitude < historical 90th percentile
    5. 60-day close>MA50 count >= 30 days
    """
    scores = {}
    cal = get_trade_calendar("20140101", t_date)
    all_dates = cal["trade_date"].tolist()
    if len(all_dates) < 200:
        return pd.Series(dtype=float)

    t_idx = all_dates.index(t_date) if t_date in all_dates else len(all_dates) - 1
    date_60d_ago = all_dates[max(0, t_idx - 60)]
    date_200d_ago = all_dates[max(0, t_idx - 200)]

    industry_returns = defaultdict(list)

    for code in codes:
        df = _load_price_data(code)
        if len(df) < 200:
            continue
        df_window = df[(df.index >= date_200d_ago) & (df.index <= all_dates[t_idx])]
        if len(df_window) < 200:
            continue

        close = df_window["close"]
        last_close = close.iloc[-1]
        ma50 = close.rolling(50).mean().iloc[-1]
        ma200 = close.rolling(200).mean().iloc[-1]

        # Condition 2 & 3
        if not (last_close > ma50 and ma50 > ma200):
            continue

        # Condition 4: amplitude
        if "high" in df_window.columns and "low" in df_window.columns:
            amp = (df_window["high"] - df_window["low"]) / df_window["close"]
            amp_30d_mean = amp.iloc[-30:].mean()
            amp_90pct = amp.quantile(0.9)
            if amp_30d_mean >= amp_90pct:
                continue

        # Condition 5: 60-day persistence
        above_ma = (close > close.rolling(50).mean()).iloc[-60:].sum()
        if above_ma < MOMENTUM_DAYS_ABOVE_MA:
            continue

        # RPS60 calculation
        p60 = close[close.index <= date_60d_ago]
        if len(p60) == 0:
            continue
        ret_60d = last_close / p60.iloc[-1] - 1

        ind = industry_map.get(code, "未知")
        industry_returns[ind].append((code, ret_60d))

    # Condition 1: RPS60 percentile check (intra-industry)
    for ind, items in industry_returns.items():
        rets = [r for _, r in items]
        if len(rets) < 10:
            continue
        for code, ret in items:
            pct = sum(1 for r in rets if r <= ret) / len(rets) * 100
            if pct >= RPS60_MIN:
                scores[code] = ret

    if not scores:
        return pd.Series(dtype=float)

    result = pd.Series(scores)
    zscored = result.groupby(lambda c: industry_map.get(c, "未知")).transform(_zscore)
    return zscored


def compute_S4(t_date: str, codes: list[str], industry_map: dict[str, str]) -> pd.Series:
    """
    S4 行业趋势共振。三个条件全部满足 → Z-Score复合得分。

    Conditions:
    1. Industry 60d median return ranks in top 40% of all industries
    2. Intra-industry breadth (20d positive return %) > 50%
    3. Intra-industry new-high near 52-week high % > median across all industries
    """
    cal = get_trade_calendar("20140101", t_date)
    all_dates = cal["trade_date"].tolist()
    if len(all_dates) < 250:
        return pd.Series(dtype=float)

    t_idx = all_dates.index(t_date) if t_date in all_dates else len(all_dates) - 1
    date_60d_ago = all_dates[max(0, t_idx - 60)]
    date_250d_ago = all_dates[max(0, t_idx - 250)]
    date_20d_ago = all_dates[max(0, t_idx - 20)]

    ind_codes = defaultdict(list)
    for c in codes:
        ind_codes[industry_map.get(c, "未知")].append(c)

    industry_stats = {}
    for ind, ind_cs in ind_codes.items():
        rets_60d, rets_20d = [], []
        near_high_count = 0
        total = 0

        for code in ind_cs:
            df = _load_price_data(code)
            if len(df) < 250:
                continue
            df_window = df[(df.index >= date_250d_ago) & (df.index <= all_dates[t_idx])]
            if len(df_window) < 60:
                continue
            close = df_window["close"]
            total += 1

            p60 = close[close.index <= date_60d_ago]
            if len(p60) > 0:
                rets_60d.append(close.iloc[-1] / p60.iloc[-1] - 1)

            p20 = close[close.index <= date_20d_ago]
            if len(p20) > 0:
                rets_20d.append(close.iloc[-1] / p20.iloc[-1] - 1)

            high_250 = close.rolling(250).max().iloc[-1]
            if high_250 > 0 and (high_250 - close.iloc[-1]) / high_250 < 0.05:
                near_high_count += 1

        if total < 5:
            continue

        med_ret = np.median(rets_60d) if rets_60d else 0
        breadth = sum(1 for r in rets_20d if r > 0) / len(rets_20d) if rets_20d else 0
        nh_pct = near_high_count / total

        industry_stats[ind] = {"ret_60d": med_ret, "breadth": breadth, "new_high_pct": nh_pct}

    all_nh = [s["new_high_pct"] for s in industry_stats.values()]
    median_nh = np.median(all_nh) if all_nh else 0

    # Condition 1: top 40% by industry return
    rets_sorted = sorted(industry_stats.items(), key=lambda x: x[1]["ret_60d"], reverse=True)
    n_top = max(1, int(len(rets_sorted) * SECTOR_TOP_PCT))
    top_inds = {ind for ind, _ in rets_sorted[:n_top]}

    sector_scores = {}
    for ind, s in industry_stats.items():
        if ind in top_inds and s["breadth"] > SECTOR_BREADTH_MIN and s["new_high_pct"] > median_nh:
            sector_scores[ind] = 0.7 * s["ret_60d"] + 0.3 * s["breadth"]

    if not sector_scores:
        return pd.Series(dtype=float)

    s4_z = _zscore(pd.Series(sector_scores))
    result = {}
    for ind, z in s4_z.items():
        for code in ind_codes.get(ind, []):
            result[code] = z

    return pd.Series(result)


def _fetch_one_stock_fin(code: str) -> list[dict]:
    """Download financial indicators for a single stock. Returns list of row dicts."""
    try:
        df = ak.stock_financial_analysis_indicator(
            symbol=code, start_year=str(FIN_START_YEAR)
        )
        rows = []
        for _, row in df.iterrows():
            roe = row.get("加权净资产收益率(%)")
            ocf = row.get("经营现金净流量对销售收入比率(%)")
            rows.append({
                "code": code,
                "date": str(row["日期"])[:10],
                "roe_weighted": float(roe) if roe is not None and str(roe) != "nan" else np.nan,
                "ocf_to_revenue": float(ocf) if ocf is not None and str(ocf) != "nan" else np.nan,
            })
        return rows
    except Exception:
        return []


def _load_financial_data() -> pd.DataFrame:
    """
    Load financial data from cache or download via AKShare in parallel.
    Columns: code, date, roe_weighted, ocf_to_revenue
    """
    if os.path.exists(FIN_CACHE):
        return pd.read_csv(FIN_CACHE, dtype={"code": str})

    from universe import get_stock_list
    stocks = get_stock_list()
    codes = stocks["code"].tolist()

    records = []
    workers = 5
    completed = 0

    logger.info(f"开始下载 {len(codes)} 只股票财务数据 ({workers}线程并行)...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one_stock_fin, code): code for code in codes}
        for fut in as_completed(futures):
            completed += 1
            try:
                rows = fut.result()
                records.extend(rows)
            except Exception:
                pass
            if completed % 500 == 0:
                logger.info(f"财务数据进度: {completed}/{len(codes)}")

    df = pd.DataFrame(records)
    os.makedirs(os.path.dirname(FIN_CACHE), exist_ok=True)
    df.to_csv(FIN_CACHE, index=False)
    logger.info(f"财务数据已缓存: {len(df)} 条记录, {df['code'].nunique()} 只股票")
    return df


def compute_S5(t_date: str, codes: list[str], industry_map: dict[str, str]) -> pd.Series:
    """
    S5 盈利稳定性。近3年加权ROE标准差，行业内反向Z-Score。
    Lower std = higher score.
    """
    fin = _load_financial_data()
    fin["date"] = pd.to_datetime(fin["date"])
    cutoff = pd.to_datetime(t_date, format="%Y%m%d")
    fin = fin[fin["date"] <= cutoff]

    roe_std = {}
    for code in codes:
        code_fin = fin[fin["code"] == code]
        roe = code_fin["roe_weighted"].dropna()
        if len(roe) < ROE_MIN_QUARTERS:
            continue
        roe_std[code] = roe.tail(12).std()

    if not roe_std:
        return pd.Series(dtype=float)

    result = pd.Series(roe_std)
    zscored = result.groupby(lambda c: industry_map.get(c, "未知")).transform(lambda x: -_zscore(x))
    return zscored


def compute_S7(t_date: str, codes: list[str], industry_map: dict[str, str]) -> pd.Series:
    """
    S7 现金流质量。最新季度经营现金流/营收，行业内Z-Score。
    Negative values -> NaN.
    """
    fin = _load_financial_data()
    fin["date"] = pd.to_datetime(fin["date"])
    cutoff = pd.to_datetime(t_date, format="%Y%m%d")
    fin = fin[fin["date"] <= cutoff]

    ocf_ratio = {}
    for code in codes:
        code_fin = fin[fin["code"] == code]
        ocf = code_fin["ocf_to_revenue"].dropna()
        if len(ocf) == 0:
            continue
        latest = ocf.iloc[-1]
        if latest > 0:
            ocf_ratio[code] = latest

    if not ocf_ratio:
        return pd.Series(dtype=float)

    result = pd.Series(ocf_ratio)
    zscored = result.groupby(lambda c: industry_map.get(c, "未知")).transform(_zscore)
    return zscored


def compute_alpha(t_date: str, codes: list[str]) -> dict[str, float]:
    """
    Alpha = mean of non-NaN signals S3, S4, S5, S7.
    Industry map is shared across all signals.
    """
    industry_map = get_sw_industry()

    s3 = compute_S3(t_date, codes, industry_map)
    s4 = compute_S4(t_date, codes, industry_map)
    s5 = compute_S5(t_date, codes, industry_map)
    s7 = compute_S7(t_date, codes, industry_map)

    logger.info(
        f"S3:{s3.notna().sum()}/{len(codes)} "
        f"S4:{s4.notna().sum()}/{len(codes)} "
        f"S5:{s5.notna().sum()}/{len(codes)} "
        f"S7:{s7.notna().sum()}/{len(codes)}"
    )

    alpha = {}
    for code in codes:
        vals = []
        for s in [s3, s4, s5, s7]:
            if code in s.index and not pd.isna(s[code]):
                vals.append(s[code])
        if vals:
            alpha[code] = sum(vals) / len(vals)

    return alpha
