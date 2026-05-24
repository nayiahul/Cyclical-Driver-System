"""WACC 计算 — Beta/ERP/债务成本/加权资本成本。

compute_wacc(code, t_date) 是主要入口。
"""
import numpy as np
import pandas as pd
from typing import Optional
from loguru import logger
import statsmodels.api as sm

import os
from growth_os.config import WACC_CONFIG
from growth_os.data import (
    get_price_data,
    get_risk_free_rate,
    get_csi300_pe_ttm,
    get_financial_snapshot,
    get_market_cap,
    load_tdx_financials,
)

_CSI300_CACHE = None


def _load_csi300() -> pd.DataFrame | None:
    """加载沪深300日线（从项目缓存 index_399300.csv）。"""
    global _CSI300_CACHE
    if _CSI300_CACHE is not None:
        return _CSI300_CACHE
    paths = [
        "data/cache/index_399300.csv",
        os.path.join(os.path.dirname(__file__), "..", "data/cache/index_399300.csv"),
    ]
    for p in paths:
        if os.path.exists(p):
            _CSI300_CACHE = pd.read_csv(p, parse_dates=["date"])
            logger.info(f"沪深300行情加载: {len(_CSI300_CACHE)} 行")
            return _CSI300_CACHE
    return None


def compute_beta(code: str, t_date: str, window: int = None) -> float | None:
    """OLS 回归计算 Beta。

    个股日收益率 ~ 沪深300日收益率，窗口默认504交易日(≈24个月)。
    """
    if window is None:
        window = WACC_CONFIG["beta_window_days"]

    stock_df = get_price_data(code)
    if stock_df is None:
        return None

    # 沪深300: 从项目缓存 index_399300.csv 读取
    csi300_df = _load_csi300()
    if csi300_df is None:
        logger.warning(f"无法获取沪深300行情，Beta不可算")
        return None

    t_dt = pd.Timestamp(t_date)

    stock_df = stock_df[stock_df["date"] <= t_dt].tail(window)
    csi300_df = csi300_df[csi300_df["date"] <= t_dt].tail(window)

    if len(stock_df) < 126:  # 至少需要半年数据
        return None

    # 对齐日期
    stock_ret = stock_df.set_index("date")["close"].pct_change().dropna()
    market_ret = csi300_df.set_index("date")["close"].pct_change().dropna()

    common_dates = stock_ret.index.intersection(market_ret.index)
    if len(common_dates) < 60:  # 至少60个有效点
        return None

    X = market_ret.loc[common_dates].values
    y = stock_ret.loc[common_dates].values

    # 去掉极端值
    mask = (np.abs(X) < 0.10) & (np.abs(y) < 0.10)  # 排除涨跌停
    X, y = X[mask], y[mask]

    if len(X) < 60:
        return None

    X_sm = sm.add_constant(X)
    try:
        model = sm.OLS(y, X_sm).fit()
        beta = model.params[1]
        return float(beta)
    except Exception:
        return None


def compute_erp(t_date: str) -> float:
    """计算股权风险溢价 ERP。

    优先用 Damodaran A股参考值(每月更新)。
    盈利收益率法仅作交叉校验(1/PE - rf)，在3%~10%区间内才采纳。
    """
    rf = get_risk_free_rate()
    erp_damo = WACC_CONFIG["erp_damodaran_default"]

    pe_csi300 = get_csi300_pe_ttm()
    earnings_yield = (1 / pe_csi300) * 100 if pe_csi300 > 0 else 5.0
    erp_ey = earnings_yield - rf

    # 盈利收益率法仅在合理区间内使用，否则纯用Damodaran
    if 3.0 <= erp_ey <= 10.0:
        return (erp_ey + erp_damo) / 2  # blend
    else:
        return erp_damo


def compute_cost_of_debt(code: str, t_date: str) -> float | None:
    """计算债务成本 r_d = 利息费用 / 有息负债。

    有息负债 = 短期借款 + 长期借款 + 应付债券 + 一年内到期非流动负债 + 租赁负债
    """
    snap = get_financial_snapshot(t_date)
    row = snap[snap["code"] == code]
    if row.empty:
        return None
    row = row.iloc[0]

    interest = row.get("interest_expense")
    if pd.isna(interest) or interest == 0:
        # 回退：用财务费用(扣除利息收入)近似
        finance_exp = row.get("finance_expense")
        interest_income = row.get("interest_income")
        if pd.isna(finance_exp):
            return None
        interest = abs(finance_exp)
        if not pd.isna(interest_income):
            interest = max(interest - abs(interest_income), 0)
        if interest == 0:
            return None

    # 有息负债
    debt_components = [
        row.get("short_term_loan"),
        row.get("long_term_loan"),
        row.get("bonds_payable"),
        row.get("noncurrent_liab_due_1y"),
        row.get("lease_liability"),
    ]
    total_debt = sum(abs(v) for v in debt_components if not pd.isna(v))
    if total_debt == 0:
        return None

    r_d = abs(interest) / total_debt
    return min(float(r_d), 0.20)  # 上限20%


def compute_wacc(code: str, t_date: str) -> float | None:
    """计算加权平均资本成本 WACC。

    WACC = E/(D+E) * r_e  +  D/(D+E) * r_d * (1 - tax_rate)

    r_e = r_f + beta * ERP  (CAPM)

    Returns:
        年化 WACC (百分比), e.g. 8.5 = 8.5%
    """
    rf = get_risk_free_rate()
    erp = compute_erp(t_date)
    beta = compute_beta(code, t_date)
    r_d = compute_cost_of_debt(code, t_date)

    if beta is None:
        return None
    if r_d is None:
        r_d = 0.04  # 债务成本默认4%

    r_e = rf + beta * erp

    # 资本结构
    market_cap = get_market_cap(code, t_date)
    snap = get_financial_snapshot(t_date)
    row = snap[snap["code"] == code]
    if row.empty:
        return None
    row = row.iloc[0]

    debt_components = [
        row.get("short_term_loan"),
        row.get("long_term_loan"),
        row.get("bonds_payable"),
        row.get("noncurrent_liab_due_1y"),
        row.get("lease_liability"),
    ]
    D = sum(abs(v) for v in debt_components if not pd.isna(v))

    if market_cap is None or market_cap <= 0:
        E = row.get("equity_parent", 0) or row.get("total_assets", 0) - D
        if E <= 0:
            return r_e  # 无债务时的回退
    else:
        E = market_cap

    V = E + D
    if V <= 0:
        return r_e

    # A 股有效税率约 15-25%，取名义税率 25%
    tax_rate = 0.25

    wacc = (E / V) * r_e + (D / V) * r_d * (1 - tax_rate)
    return float(wacc)
