"""等权回测引擎"""

import os
import time
from dataclasses import dataclass

import akshare as ak
import numpy as np
import pandas as pd
from loguru import logger

from config.params import (
    END_DATE,
    INITIAL_CAPITAL,
    MAX_SINGLE_WEIGHT,
    MIN_HOLDINGS,
    START_DATE,
    TOTAL_COST_RATE,
)
from trade_calendar import get_rebalance_dates, get_t_date, get_trade_calendar
from universe import get_universe


_PRICE_CACHE: dict[str, pd.Series] = {}


@dataclass
class BacktestResult:
    nav_series: pd.Series  # daily NAV, index=date
    daily_returns: pd.Series  # daily returns
    trades: pd.DataFrame  # trade records
    stats: dict  # summary statistics


def _load_price_cache(code: str) -> pd.Series:
    """Load daily close prices for a stock, caching to CSV and in-memory."""
    if code in _PRICE_CACHE:
        return _PRICE_CACHE[code]

    cache_path = f"data/cache/daily_prices/{code}.csv"
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, dtype={"date": str})
            prices = df.set_index("date")["close"]
            _PRICE_CACHE[code] = prices
            return prices
        except Exception:
            logger.warning(f"{code} 缓存文件损坏，重新下载")

    try:
        hist = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date="20140101",
            end_date="20251231",
            adjust="qfq",
        )
        time.sleep(0.1)  # be nice to akshare API
        df = hist[["日期", "收盘"]].copy()
        df.columns = ["date", "close"]
        df["date"] = df["date"].str.replace("-", "")
        df["close"] = df["close"].astype(float)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        df.to_csv(cache_path, index=False)
        prices = df.set_index("date")["close"]
        _PRICE_CACHE[code] = prices
        return prices
    except Exception:
        logger.warning(f"获取 {code} 价格数据失败")
        empty = pd.Series(dtype=float)
        _PRICE_CACHE[code] = empty
        return empty


def _get_close_price(code: str, date: str) -> float | None:
    """Get close price for a stock on a date.

    If the exact date is missing, falls back to the most recent available
    price on or before the requested date.
    """
    prices = _load_price_cache(code)
    if len(prices) == 0:
        return None
    if date in prices.index:
        val = prices[date]
        if pd.isna(val):
            return None
        return float(val)
    available = prices[prices.index <= date]
    if len(available) > 0:
        val = available.iloc[-1]
        if pd.isna(val):
            return None
        return float(val)
    return None


def _compute_stats(nav: pd.Series, daily_returns: pd.Series) -> dict:
    """Compute performance statistics from NAV and daily returns series."""
    trading_days_per_year = 252
    total_days = len(daily_returns)
    years = total_days / trading_days_per_year

    total_return = (nav.iloc[-1] / nav.iloc[0]) - 1
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    annual_vol = daily_returns.std() * np.sqrt(trading_days_per_year)
    risk_free = 0.02
    sharpe = (annual_return - risk_free) / annual_vol if annual_vol > 0 else 0

    cummax = nav.cummax()
    drawdown = (nav - cummax) / cummax
    max_drawdown = drawdown.min()
    calmar = (
        annual_return / abs(max_drawdown) if max_drawdown != 0 else 0
    )
    win_rate = (
        (daily_returns > 0).sum() / len(daily_returns)
        if len(daily_returns) > 0
        else 0
    )

    return {
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "annual_volatility": round(annual_vol, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown": round(max_drawdown, 4),
        "calmar_ratio": round(calmar, 4),
        "win_rate": round(win_rate, 4),
        "years": round(years, 2),
        "initial_nav": round(nav.iloc[0], 2),
        "final_nav": round(nav.iloc[-1], 2),
    }


def run_backtest(
    start: str = START_DATE,
    end: str = END_DATE,
    initial_capital: float = INITIAL_CAPITAL,
) -> BacktestResult:
    """Run equal-weight monthly rebalance backtest.

    Args:
        start: Start date "YYYYMMDD".
        end: End date "YYYYMMDD".
        initial_capital: Starting cash.

    Returns:
        BacktestResult with NAV series, daily returns, trade log, and stats.
    """
    rebalance_dates = set(get_rebalance_dates(start, end))
    cal = get_trade_calendar(start, end)
    trading_days = cal["trade_date"].tolist()

    if not trading_days:
        raise ValueError(f"回测区间 {start} ~ {end} 内无交易日")

    logger.info(
        f"回测区间: {start} ~ {end}, "
        f"{len(trading_days)} 个交易日, "
        f"{len(rebalance_dates)} 个调仓日"
    )

    holdings: dict[str, float] = {}
    cash = initial_capital
    nav_records: list[tuple[str, float]] = []
    trade_records: list[dict] = []

    for i, day in enumerate(trading_days):
        if day in rebalance_dates:
            t_date = get_t_date(day)
            universe_df = get_universe(t_date)
            target_codes = universe_df["code"].tolist()
            n = len(target_codes)

            if n == 0:
                logger.warning(f"{day}: universe 为空，跳过调仓")
            else:
                if n < MIN_HOLDINGS:
                    logger.warning(
                        f"{day}: universe 仅 {n} 只股票, "
                        f"低于 MIN_HOLDINGS={MIN_HOLDINGS}"
                    )

                # Equal target weights with 8% cap
                target_weights = {
                    code: min(1.0 / n, MAX_SINGLE_WEIGHT)
                    for code in target_codes
                }

                # Step 1: Sell holdings not in the new target universe
                for code in list(holdings.keys()):
                    if code in target_weights:
                        continue
                    shares = holdings[code]
                    price = _get_close_price(code, day)
                    if price is None or price <= 0:
                        logger.warning(
                            f"{day}: {code} 无有效价格，保留持仓不卖出"
                        )
                        continue
                    value = shares * price
                    cost = value * TOTAL_COST_RATE
                    cash += value - cost
                    trade_records.append(
                        {
                            "date": day,
                            "code": code,
                            "direction": "sell",
                            "qty": int(shares),
                            "price": round(price, 2),
                            "cost": round(cost, 2),
                        }
                    )
                    del holdings[code]

                # Step 2: Reconcile remaining holdings to target weights
                # Compute total capital before making any target trades
                holdings_value = 0.0
                for code, shares in holdings.items():
                    price = _get_close_price(code, day)
                    if price is not None and price > 0:
                        holdings_value += shares * price

                total_capital = cash + holdings_value
                if total_capital <= 0:
                    logger.warning(
                        f"{day}: 总资金为 {total_capital:.2f}，跳过调仓"
                    )
                else:
                    for code in target_codes:
                        weight = target_weights[code]
                        target_value = total_capital * weight
                        current_shares = holdings.get(code, 0.0)
                        price = _get_close_price(code, day)

                        if price is None or price <= 0:
                            if current_shares > 0:
                                logger.warning(
                                    f"{day}: {code} 无有效价格，保留现有持仓"
                                )
                            continue

                        current_value = current_shares * price
                        diff = target_value - current_value

                        if abs(diff) < 0.01:
                            continue

                        if diff > 0:
                            # Buy to reach target
                            buy_qty = int(diff / price)
                            if buy_qty <= 0:
                                continue
                            cost = buy_qty * price * TOTAL_COST_RATE
                            total_spent = buy_qty * price + cost
                            if total_spent > cash:
                                # Scale down if insufficient cash
                                buy_qty = int(
                                    cash / (price * (1 + TOTAL_COST_RATE))
                                )
                                if buy_qty <= 0:
                                    continue
                                cost = buy_qty * price * TOTAL_COST_RATE
                                total_spent = buy_qty * price + cost
                            cash -= total_spent
                            holdings[code] = (
                                holdings.get(code, 0.0) + buy_qty
                            )
                            trade_records.append(
                                {
                                    "date": day,
                                    "code": code,
                                    "direction": "buy",
                                    "qty": buy_qty,
                                    "price": round(price, 2),
                                    "cost": round(cost, 2),
                                }
                            )
                        else:
                            # Sell down toward target
                            sell_qty = int(
                                min(current_shares, -diff / price)
                            )
                            if sell_qty <= 0:
                                continue
                            cost = sell_qty * price * TOTAL_COST_RATE
                            cash += sell_qty * price - cost
                            remaining = current_shares - sell_qty
                            if remaining <= 0:
                                del holdings[code]
                            else:
                                holdings[code] = remaining
                            trade_records.append(
                                {
                                    "date": day,
                                    "code": code,
                                    "direction": "sell",
                                    "qty": sell_qty,
                                    "price": round(price, 2),
                                    "cost": round(cost, 2),
                                }
                            )

            # Clean up any zero-share positions
            for code in list(holdings.keys()):
                if holdings[code] <= 0:
                    del holdings[code]

        # --- Daily NAV ---
        equity = cash
        for code, shares in holdings.items():
            price = _get_close_price(code, day)
            if price is not None and price > 0:
                equity += shares * price
        nav_records.append((day, equity))

        # Progress log every 500 days
        if (i + 1) % 500 == 0:
            logger.info(
                f"进度: {day} | 持仓 {len(holdings)} 只 | "
                f"NAV {equity:,.0f} | 现金 {cash:,.0f}"
            )

    # --- Build result ---
    nav_index = [r[0] for r in nav_records]
    nav_values = [r[1] for r in nav_records]
    nav_series = pd.Series(nav_values, index=nav_index, dtype=float)
    daily_returns = nav_series.pct_change().dropna()
    trades_df = (
        pd.DataFrame(trade_records) if trade_records else pd.DataFrame()
    )
    stats = _compute_stats(nav_series, daily_returns)

    logger.info(
        f"回测完成: {len(trading_days)} 天, {len(trade_records)} 笔交易"
    )
    logger.info(
        f"累计收益: {stats['total_return']:.2%}, "
        f"年化: {stats['annual_return']:.2%}, "
        f"夏普: {stats['sharpe_ratio']:.2f}, "
        f"最大回撤: {stats['max_drawdown']:.2%}"
    )

    return BacktestResult(
        nav_series=nav_series,
        daily_returns=daily_returns,
        trades=trades_df,
        stats=stats,
    )
