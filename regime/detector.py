"""市场周期状态判定"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from loguru import logger

from config.params import (
    BREADTH_BEAR, BREADTH_BULL,
    BULL_VOTE, INDEX_DROP_20D,
    MARGIN_WEEKLY_DROP, NEW_HIGH_BEAR, NEW_HIGH_BULL,
    PE_CHANGE_BEAR, PE_CHANGE_BULL,
    STRUCT_TO_BULL_CONFIRM, BEAR_WEEKLY_CONFIRM,
)
from regime.indicators import (
    index_trend, liquidity, market_breadth, new_high_ratio, risk_appetite,
)
from trade_calendar import get_trade_calendar


@dataclass
class RegimeResult:
    regime: str        # "BULL" | "STRUCT" | "BEAR"
    score: float       # 0.0 - 1.0
    details: dict      # 各维度布尔判定


def detect_regime(t_date: str) -> RegimeResult:
    """
    给定月末确认日，返回下月生效的 Regime。

    判定规则：
    1. 先检查极端快速通道（指数急跌、流动性枯竭）
    2. 再计算5维度布尔判定
    3. 根据命中项数判定状态
    """
    cal = get_trade_calendar("20140101", t_date)
    trade_dates = cal["trade_date"].tolist()

    # 计算5维度指标
    it = index_trend(trade_dates)
    mb = market_breadth(trade_dates)
    nh = new_high_ratio(trade_dates)
    ra = risk_appetite(trade_dates)
    liq = liquidity(trade_dates)

    # 取最后一个月的值
    t_ym = t_date[:6]
    if t_ym not in it.index:
        return RegimeResult(regime="STRUCT", score=0.5, details={})

    idx_close = float(it.loc[t_ym, "close"].iloc[-1])
    idx_above_ma200 = bool(it.loc[t_ym, "above_ma200"].iloc[-1])
    idx_ma60_gt_ma120 = bool(it.loc[t_ym, "ma60_gt_ma120"].iloc[-1])
    breadth_val = float(mb.loc[t_ym, "breadth_ratio"].iloc[-1])
    nh_val = float(nh.loc[t_ym, "dist_from_high"].iloc[-1])
    pe_change = float(ra.loc[t_ym, "pe_60d_change"].iloc[-1])
    margin_weekly = float(liq.loc[t_ym, "margin_weekly_change"].iloc[-1])
    flow_3week = float(liq.loc[t_ym, "flow_3week"].iloc[-1])

    # === 极端快速通道 ===
    # 指数急跌：滚动20日跌幅 > 15%
    if len(it) >= 20:
        close_20d_ago = float(it["close"].iloc[-21])
        drop_20d = (idx_close - close_20d_ago) / close_20d_ago
        if drop_20d < -INDEX_DROP_20D:
            logger.warning(f"极端通道触发: 指数20日跌幅 {drop_20d:.1%} @ {t_date}")
            return _extreme_bear(t_date)

    # 流动性枯竭：融资余额单周变化 < -10%
    if not np.isnan(margin_weekly) and margin_weekly < MARGIN_WEEKLY_DROP:
        logger.warning(f"极端通道触发: 融资余额周变化 {margin_weekly:.1%} @ {t_date}")
        return _extreme_bear(t_date)

    # === 5维度布尔判定 ===
    # 牛市条件
    bull_details = {
        "index": idx_above_ma200 and idx_ma60_gt_ma120,
        "breadth": breadth_val > BREADTH_BULL,
        "new_high": nh_val < NEW_HIGH_BULL,
        "risk": not np.isnan(pe_change) and pe_change > PE_CHANGE_BULL,
        "liquidity": not np.isnan(flow_3week) and flow_3week > 0,
    }
    bull_count = sum(bull_details.values())

    # 熊市条件
    bear_details = {
        "index": (not idx_above_ma200) and (not idx_ma60_gt_ma120),
        "breadth": not np.isnan(breadth_val) and breadth_val < BREADTH_BEAR,
        "new_high": not np.isnan(nh_val) and nh_val > NEW_HIGH_BEAR,
        "risk": not np.isnan(pe_change) and pe_change < PE_CHANGE_BEAR,
        "liquidity": not np.isnan(flow_3week) and flow_3week < -2,
    }
    bear_count = sum(bear_details.values())

    # RegimeScore: 牛市条件满足比例
    score = bull_count / 5.0
    if bear_count >= 3:
        score = min(score, 0.35)

    # 状态判定
    if bear_count >= 4:
        regime = "BEAR"
    elif bull_count >= BULL_VOTE:
        regime = "BULL"
    else:
        regime = "STRUCT"

    return RegimeResult(regime=regime, score=score, details={
        "bull": bull_details,
        "bear": bear_details,
        "bull_count": bull_count,
        "bear_count": bear_count,
    })


def _extreme_bear(t_date: str) -> RegimeResult:
    """极端通道熊市"""
    return RegimeResult(
        regime="BEAR",
        score=0.0,
        details={"extreme": True, "bull_count": 0, "bear_count": 5},
    )
