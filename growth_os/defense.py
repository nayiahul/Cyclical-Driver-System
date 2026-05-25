"""DEFENSE 模式防御资产收益计算。

不选个股，直接切资产类别：
  40% 中证红利 (000922) + 40% 国债ETF (511010) + 20% 现金 (年化1.5%)
"""
from __future__ import annotations

import os
import warnings

import akshare as ak
import pandas as pd
from loguru import logger

warnings.filterwarnings("ignore")

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache")

# 防御资产配置
DEFENSE_WEIGHTS = {
    "dividend": 0.40,   # 中证红利
    "bond": 0.40,       # 国债ETF
    "cash": 0.20,       # 现金
}

CASH_ANNUAL_RATE = 0.015  # 年化 1.5%


# --- 数据加载（缓存） ---

_DIVIDEND_CACHE: pd.DataFrame | None = None
_BOND_CACHE: pd.DataFrame | None = None


def _load_dividend_index() -> pd.DataFrame:
    """加载中证红利指数日线。"""
    global _DIVIDEND_CACHE
    if _DIVIDEND_CACHE is not None:
        return _DIVIDEND_CACHE

    cache_path = os.path.join(_CACHE_DIR, "index_000922_dividend.csv")
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
        _DIVIDEND_CACHE = df
        return df

    df = ak.stock_zh_index_daily(symbol="sh000922")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    os.makedirs(_CACHE_DIR, exist_ok=True)
    df.to_csv(cache_path, index=False)
    _DIVIDEND_CACHE = df
    return df


def _load_bond_etf() -> pd.DataFrame:
    """加载国债ETF日线。"""
    global _BOND_CACHE
    if _BOND_CACHE is not None:
        return _BOND_CACHE

    cache_path = os.path.join(_CACHE_DIR, "etf_511010_bond.csv")
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
        _BOND_CACHE = df
        return df

    df = ak.fund_etf_hist_em(
        symbol="511010", period="daily",
        start_date="20180101", end_date="20261231",
    )
    df = df.rename(columns={"日期": "date", "收盘": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df = df[["date", "close"]].sort_values("date")
    os.makedirs(_CACHE_DIR, exist_ok=True)
    df.to_csv(cache_path, index=False)
    _BOND_CACHE = df
    return df


# --- 收益计算 ---

def _get_price_on_or_before(df: pd.DataFrame, target_date: pd.Timestamp,
                            col: str = "close") -> float | None:
    """获取目标日期当天或之前最近的有效收盘价。"""
    before = df[df["date"] <= target_date]
    if before.empty:
        return None
    return float(before.iloc[-1][col])


def get_defense_basket_return(hold_date: str, forward_months: int,
                              max_date: str) -> float:
    """计算防御资产组合在持有期的总收益。

    Args:
        hold_date: 建仓日期 YYYYMMDD
        forward_months: 持有月数
        max_date: 数据截止日 YYYYMMDD

    Returns:
        持有期收益率 (小数), e.g. 0.03 = 3%
    """
    t0 = pd.Timestamp(hold_date)
    t1 = t0 + pd.DateOffset(months=forward_months)
    t1 = min(t1, pd.Timestamp(max_date))

    total_return = 0.0

    # 1. 中证红利
    div_df = _load_dividend_index()
    p0_div = _get_price_on_or_before(div_df, t0)
    p1_div = _get_price_on_or_before(div_df, t1)
    if p0_div and p1_div and p0_div > 0:
        div_ret = p1_div / p0_div - 1
    else:
        div_ret = 0.0
    total_return += DEFENSE_WEIGHTS["dividend"] * div_ret

    # 2. 国债 ETF
    bond_df = _load_bond_etf()
    p0_bond = _get_price_on_or_before(bond_df, t0)
    p1_bond = _get_price_on_or_before(bond_df, t1)
    if p0_bond and p1_bond and p0_bond > 0:
        bond_ret = p1_bond / p0_bond - 1
    else:
        bond_ret = 0.0
    total_return += DEFENSE_WEIGHTS["bond"] * bond_ret

    # 3. 现金（固定年化）
    years = forward_months / 12.0
    cash_ret = (1 + CASH_ANNUAL_RATE) ** years - 1
    total_return += DEFENSE_WEIGHTS["cash"] * cash_ret

    return float(total_return)


# --- 诊断 ---

def main():
    import argparse
    parser = argparse.ArgumentParser(description="防御资产诊断")
    parser.add_argument("--date", type=str, default="20220331")
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--max-date", type=str, default="20260501")
    args = parser.parse_args()

    ret = get_defense_basket_return(args.date, args.months, args.max_date)
    print(f"防御组合 {args.date} → +{args.months}月: {ret*100:+.1f}%")

    # 同期对比
    div = _load_dividend_index()
    bond = _load_bond_etf()
    t0 = pd.Timestamp(args.date)
    t1 = t0 + pd.DateOffset(months=args.months)
    p0 = _get_price_on_or_before(div, t0)
    p1 = _get_price_on_or_before(div, t1)
    if p0 and p1:
        print(f"  中证红利: {p1/p0-1:+.2%}")
    p0b = _get_price_on_or_before(bond, t0)
    p1b = _get_price_on_or_before(bond, t1)
    if p0b and p1b:
        print(f"  国债ETF: {p1b/p0b-1:+.2%}")


if __name__ == "__main__":
    main()
