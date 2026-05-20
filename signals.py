"""Alpha信号计算：S3(动量) S4(行业共振) S5(盈利稳定性) S7(现金流质量)"""
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import akshare as ak
import numpy as np
import pandas as pd
from loguru import logger

from orthogonalizer import symmetric_orthogonalize
from weights import IRWeightManager
from data_governance import filter_available_reports, filter_available_reports_dash

from config.params import (
    FIN_START_YEAR, MOMENTUM_DAYS_ABOVE_MA, ROE_MIN_QUARTERS,
    RPS60_MIN, SECTOR_BREADTH_MIN, SECTOR_TOP_PCT,
)
from industry import get_sw_industry
from trade_calendar import get_trade_calendar

FIN_CACHE = "data/cache/financial_data.csv"
_ir_manager = IRWeightManager(["S3", "S4", "S5", "S7"], window=36)
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
    fin = filter_available_reports_dash(fin, "date", t_date)
    fin["date"] = pd.to_datetime(fin["date"])

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
    fin = filter_available_reports_dash(fin, "date", t_date)
    fin["date"] = pd.to_datetime(fin["date"])

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



def compute_S1(t_date: str, codes: list[str], industry_map: dict[str, str],
               return_raw: bool = False):
    """
    S1 利润加速度（简化版）。

    数据源: TDX 财务缓存 (deducted_profit_yoy, 扣非净利润同比)
    算法: 对过去3个单季度同比增速做线性回归，斜率>0且R²>0.6判定加速。
    质量防护: 经营现金流不逆利润、低基数过滤、洗大澡检测。

    字段验证状态 (2026-05-18):
    - deducted_profit_yoy (col 191): AKShare交叉验证确认为单季度同比 ✓
    - deducted_profit_q (col 233): 修复CSV缓存winsorize后数据正常 ✓

    Args:
        return_raw: 若为 True，返回 (zscored_series, raw_yoy_series) 元组。
                    用于 PEG 标准计算等需要原始增速的场景。
    """
    import os as _os
    tdx_path = "data/cache/tdx_financials.csv"
    if not _os.path.exists(tdx_path):
        return pd.Series(dtype=float)

    fin = pd.read_csv(tdx_path, dtype={"code": str, "report_date_str": str})
    fin = fin.dropna(subset=["report_date_str"])
    fin = filter_available_reports(fin, t_date)
    fin = fin[["code", "report_date_str", "deducted_profit_yoy",
               "deducted_profit_q", "operating_cash_flow"]].copy()
    fin = fin.dropna(subset=["deducted_profit_yoy"])

    scores = {}
    for code in codes:
        code_fin = fin[fin["code"] == code].sort_values("report_date_str")
        if len(code_fin) < 4:
            continue
        yoy = code_fin["deducted_profit_yoy"].values[-3:].astype(float)

        # Low base filter: last year same quarter profit < 10M → skip
        profits = code_fin["deducted_profit_q"].values[-4:].astype(float)
        if len(profits) >= 4 and abs(profits[-4]) < 1e7:
            continue

        # Trend acceleration: linear regression slope > 0, R² > 0.6
        if len(yoy) < 3:
            continue
        x = np.arange(3, dtype=float)
        y_valid = ~np.isnan(yoy)
        if y_valid.sum() < 3:
            continue
        slope, intercept = np.polyfit(x, yoy, 1)
        y_pred = slope * x + intercept
        ss_res = np.sum((yoy - y_pred) ** 2)
        ss_tot = np.sum((yoy - np.mean(yoy)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        if slope <= 0 or r2 < 0.6:
            continue

        # Bath check: operating profit not diverging from deducted profit
        # (Simplified: skip if yoy volatility > 150pp in 10 quarters)
        yoy_all = code_fin["deducted_profit_yoy"].values[-10:].astype(float)
        if len(yoy_all) >= 8:
            if np.nanstd(yoy_all) > 150:
                continue

        # OCF quality: if last 2 quarters OCF sum < 0 and profit accelerated, flag
        ocf = code_fin["operating_cash_flow"].values[-2:].astype(float)
        if len(ocf) == 2 and np.nansum(ocf) < 0:
            # Downgrade but don't fully exclude — S1 *= 0.5 via lower score
            scores[code] = yoy[-1] * 0.5
        else:
            scores[code] = yoy[-1]

    if not scores:
        if return_raw:
            return pd.Series(dtype=float), pd.Series(dtype=float)
        return pd.Series(dtype=float)

    result = pd.Series(scores)
    # 保存原始值供 PEG 等下游使用（Z-Score 化前）
    raw = result.copy() if return_raw else None

    groups = {c: industry_map.get(c, "未知") for c in result.index}
    result.index = pd.MultiIndex.from_tuples(
        [(c, groups.get(c, "未知")) for c in result.index],
        names=["code", "industry"],
    )
    zscored = result.groupby("industry").transform(_zscore)
    zscored.index = zscored.index.get_level_values("code")

    # v2.0: 周期行业 S1 降权 — 低基数效应导致 yoy 信号失真
    cyclical = {"煤炭", "钢铁", "有色金属", "基础化工", "石油石化"}
    for code in zscored.index:
        ind = industry_map.get(code, "未知")
        if ind in cyclical:
            zscored.loc[code] *= 0.7

    if return_raw:
        return zscored, raw
    return zscored


def compute_S2(t_date: str, codes: list[str], industry_map: dict[str, str]) -> pd.Series:
    """
    S2 产能扩张（简化版）。

    数据源: TDX 财务缓存 (contract_liabilities, advance_receipts, fixed_assets, capex_cash)
    算法: TTM合同负债yoy(订单) + TTM CAPEX yoy(硬扩张)，合成打分。
    排除: 银行/非银金融/房地产(一级行业)。
    """
    import os as _os
    tdx_path = "data/cache/tdx_financials.csv"
    if not _os.path.exists(tdx_path):
        return pd.Series(dtype=float)

    # 排除行业
    exclude = {"银行", "非银金融", "房地产"}

    fin = pd.read_csv(tdx_path, dtype={"code": str, "report_date_str": str})
    fin = fin.dropna(subset=["report_date_str"])
    fin = filter_available_reports(fin, t_date)
    fin = fin[["code", "report_date_str", "contract_liabilities",
               "advance_receipts", "fixed_assets", "capex_cash", "roe",
               "revenue_yoy"]].copy()

    scores = {}
    for code in codes:
        ind = industry_map.get(code, "未知")
        if ind in exclude:
            continue

        code_fin = fin[fin["code"] == code].sort_values("report_date_str")
        if len(code_fin) < 8:  # need at least 8 quarters for TTM
            continue

        # TTM values (last 4 quarters sum)
        cl = code_fin["contract_liabilities"].values.astype(float)
        ar = code_fin["advance_receipts"].values.astype(float)
        capex = code_fin["capex_cash"].values.astype(float)
        fa = code_fin["fixed_assets"].values.astype(float)
        roe = code_fin["roe"].dropna().values.astype(float)

        cl_ttm = np.nansum(cl[-4:])
        cl_ttm_prev = np.nansum(cl[-8:-4])
        ar_ttm = np.nansum(ar[-4:])
        ar_ttm_prev = np.nansum(ar[-8:-4])
        capex_ttm = np.nansum(capex[-4:])
        capex_ttm_prev = np.nansum(capex[-8:-4])

        # Order signal
        cl_yoy = (cl_ttm / cl_ttm_prev - 1) if cl_ttm_prev > 0 else 0
        ar_yoy = (ar_ttm / ar_ttm_prev - 1) if ar_ttm_prev > 0 else 0
        has_order = (cl_yoy > 0.3) or (ar_yoy > 0.3)

        # v2.0: 科技行业补充营收增速作为订单信号
        tech_inds = {"电子", "计算机", "通信", "传媒"}
        tech_order = False
        rev_avg = 0.0
        if ind in tech_inds and not has_order:
            rev_vals = code_fin["revenue_yoy"].values[-4:].astype(float)
            rev_avg = np.nanmean(rev_vals) if len(rev_vals) > 0 else 0
            if rev_avg > 20:
                has_order = True
                tech_order = True

        # Expansion signal
        capex_yoy = (capex_ttm / capex_ttm_prev - 1) if capex_ttm_prev > 0 else 0
        fa_qoq = (fa[-1] / fa[-5] - 1) if len(fa) >= 5 and fa[-5] > 0 else 0
        is_expanding = (capex_yoy > 0.2) or (fa_qoq > 0.05)

        # ROE trend: 扩产效率参考
        roe_declining = False
        if len(roe) >= 8:
            roe_recent = np.nanmean(roe[-4:])
            roe_past = np.nanmean(roe[-8:-4])
            if roe_past > 0 and roe_recent < roe_past * 0.9:
                roe_declining = True

        if not has_order and not is_expanding:
            continue

        if tech_order:
            order_score = min(rev_avg / 100, 2.0)
        else:
            order_score = max(cl_yoy, ar_yoy)

        # --- 得分合成 (v1.1 修复) ---
        if has_order and is_expanding:
            # 订单+扩产双确认 → 标准权重
            s2_raw = 0.6 * min(order_score, 3.0) + 0.4 * min(capex_yoy, 2.0)
        elif has_order and not is_expanding:
            # F: 订单先行，产能尚未跟上 → 保留信号，订单权重提高
            s2_raw = 0.8 * min(order_score, 3.0) + 0.2 * min(max(capex_yoy, 0), 2.0)
        elif not has_order and is_expanding:
            # G: 纯扩产无订单 → 更高门槛 + 效率惩罚
            if capex_yoy > 0.30:
                s2_raw = min(capex_yoy, 2.0)
                if roe_declining:
                    s2_raw *= 0.5  # ROE↓+CAPEX↑ = 无效扩张
            else:
                continue
        else:
            continue

        scores[code] = s2_raw

    if not scores:
        return pd.Series(dtype=float)

    result = pd.Series(scores)
    groups = {c: industry_map.get(c, "未知") for c in result.index}
    result.index = pd.MultiIndex.from_tuples(
        [(c, groups.get(c, "未知")) for c in result.index],
        names=["code", "industry"],
    )
    zscored = result.groupby("industry").transform(_zscore)
    zscored.index = zscored.index.get_level_values("code")
    return zscored

def compute_alpha(t_date: str, codes: list[str]) -> dict[str, float]:
    """
    Alpha = Sigma w_j * F_j
    F_j = block-symmetric orthogonalized factors
    w_j = IR dynamic weights
    """
    global _ir_manager

    industry_map = get_sw_industry()

    # Original signals
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

    # Build signal arrays (N x 1, NaN preserved)
    signal_arrays = {}
    for s_name, s_series in [("S3", s3), ("S4", s4), ("S5", s5), ("S7", s7)]:
        arr = np.full(len(codes), np.nan)
        for i, code in enumerate(codes):
            if code in s_series.index and not pd.isna(s_series[code]):
                arr[i] = s_series[code]
        signal_arrays[s_name] = arr

    # Block symmetric orthogonalization
    blocks = [["S3", "S4"], ["S5", "S7"]]
    orthogonal = symmetric_orthogonalize(signal_arrays, blocks)

    # IR weights
    weights = _ir_manager.get_weights()

    # Composite Alpha
    alpha = {}
    for i, code in enumerate(codes):
        vals = []
        ws = []
        for s_name in ["S3", "S4", "S5", "S7"]:
            val = orthogonal.get(s_name, signal_arrays[s_name])[i]
            if not np.isnan(val):
                vals.append(val)
                ws.append(weights.get(s_name, 0.25))
        if vals and sum(ws) > 0:
            alpha[code] = sum(v * w for v, w in zip(vals, ws)) / sum(ws)

    logger.info(f"Alpha IR weights: {weights}")
    return alpha


def update_ir(factor_values: dict[str, np.ndarray], forward_returns: np.ndarray):
    """Record monthly IC for next period weight calculation."""
    global _ir_manager
    _ir_manager.update(factor_values, forward_returns)


def get_current_weights() -> dict[str, float]:
    """Get current factor weights (for logging)."""
    return _ir_manager.get_weights()
