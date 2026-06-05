"""风险因子计算：Beta, Size, Volatility, Illiquidity"""
import os
import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats
from config.params import STOCKS_DIR

_PRICE_MEM_CACHE: dict[str, pd.DataFrame] = {}


def _load_price_data(code: str) -> pd.DataFrame:
    if code in _PRICE_MEM_CACHE:
        return _PRICE_MEM_CACHE[code]
    path = os.path.join(STOCKS_DIR, f"{code}.csv")
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, dtype={"code": str})
            df["date"] = pd.to_datetime(df["date"])
            result = df.set_index("date").sort_index()
            _PRICE_MEM_CACHE[code] = result
            return result
        except Exception:
            pass
    empty = pd.DataFrame()
    _PRICE_MEM_CACHE[code] = empty
    return empty


def _load_index_data() -> pd.Series:
    path = "data/cache/index_399300.csv"
    if os.path.exists(path):
        df = pd.read_csv(path, dtype={"date": str})
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")["close"]
    return pd.Series(dtype=float)


def compute_risk_factors(t_date: str, codes: list[str]) -> pd.DataFrame:
    """
    计算4个风险因子的截面向量。

    Returns:
        DataFrame index=code, columns=[beta, size, volatility, illiquidity]
    """
    cutoff = pd.to_datetime(t_date, format="%Y%m%d")
    index_close = _load_index_data()
    index_ret = index_close.pct_change().dropna()

    results = {}
    for code in codes:
        df = _load_price_data(code)
        if len(df) < 252:
            continue
        df = df[df.index <= cutoff]
        if len(df) < 252:
            continue
        close = df["close"]
        ret = close.pct_change().dropna().iloc[-252:]

        # Beta: 252日 OLS vs CSI300
        common = ret.index.intersection(index_ret.index)
        if len(common) < 100:
            continue
        ri = ret[common].values
        rm = index_ret[common].values
        slope, _, _, _, _ = stats.linregress(rm, ri)
        beta = slope

        # Size: log(close × avg_volume_20d)
        vol_col = "volume" if "volume" in df.columns else None
        avg_vol = df[vol_col].iloc[-20:].mean() if vol_col else 1e6
        size = np.log(max(close.iloc[-1] * avg_vol, 1))

        # Volatility: 60日 std
        vol60 = ret.iloc[-60:].std() if len(ret) >= 60 else ret.std()

        # Illiquidity: Amihud
        if vol_col:
            amihud_daily = np.abs(ret) / (df[vol_col] * close)
            illiq = np.log(np.mean(amihud_daily.iloc[-20:]) * 1e6 + 1e-10)
        else:
            illiq = 0.0

        results[code] = {
            "beta": beta, "size": size,
            "volatility": vol60, "illiquidity": illiq,
        }

    df = pd.DataFrame.from_dict(results, orient="index")
    df.index.name = "code"
    logger.info(f"风险因子 @ {t_date}: {len(df)}/{len(codes)} stocks")
    return df
