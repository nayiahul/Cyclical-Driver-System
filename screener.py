"""研究筛选器

基于 V4.2 三维框架（景气度/壁垒/估值）筛选标的，辅助人工深度研究。
不生成组合，不自动交易——只输出排序清单。
"""
import os
from collections import defaultdict

import numpy as np
import pandas as pd
from loguru import logger

from config.params import TOP_N_STOCKS
from industry import get_sw_industry
from trade_calendar import get_t_date, get_trade_calendar
from universe import get_universe
from valuation_filter import apply_valuation_filter
from signals import compute_S5, compute_S7, _load_price_data
from regime.detector import detect_regime


def compute_rps60(codes: list[str], t_date: str, industry_map: dict) -> dict[str, float]:
    """
    简化版 RPS60：所有股票计算60日收益的行业内百分位。
    不做五条件过滤——全景扫描用。
    """
    cal = get_trade_calendar("20140101", t_date)
    all_dates = cal["trade_date"].tolist()
    if len(all_dates) < 200:
        return {}

    t_idx = all_dates.index(t_date) if t_date in all_dates else len(all_dates) - 1
    date_60d_ago = all_dates[max(0, t_idx - 60)]

    ind_returns = defaultdict(list)
    for code in codes:
        df = _load_price_data(code)
        if len(df) < 200:
            continue
        close = df["close"]
        p60 = close[close.index <= pd.to_datetime(date_60d_ago, format="%Y%m%d")]
        if len(p60) == 0:
            continue
        ret = close.iloc[-1] / p60.iloc[-1] - 1
        ind = industry_map.get(code, "未知")
        ind_returns[ind].append((code, ret))

    scores = {}
    for ind, items in ind_returns.items():
        if len(items) < 5:
            continue
        rets = [r for _, r in items]
        for code, ret in items:
            pct = sum(1 for r in rets if r <= ret) / len(rets) * 100
            scores[code] = pct  # 0-100

    return scores


def compute_industry_momentum(codes: list[str], t_date: str, industry_map: dict) -> dict[str, float]:
    """
    简化版行业动量：每个行业的60日中位数收益。
    不做三条件过滤——全景扫描用。
    """
    cal = get_trade_calendar("20140101", t_date)
    all_dates = cal["trade_date"].tolist()
    if len(all_dates) < 200:
        return {}

    t_idx = all_dates.index(t_date) if t_date in all_dates else len(all_dates) - 1
    date_60d_ago = all_dates[max(0, t_idx - 60)]

    ind_returns = defaultdict(list)
    for code in codes:
        df = _load_price_data(code)
        if len(df) < 200:
            continue
        close = df["close"]
        p60 = close[close.index <= pd.to_datetime(date_60d_ago, format="%Y%m%d")]
        if len(p60) == 0:
            continue
        ret = close.iloc[-1] / p60.iloc[-1] - 1
        ind = industry_map.get(code, "未知")
        ind_returns[ind].append(ret)

    ind_medians = {}
    for ind, rets in ind_returns.items():
        if len(rets) >= 3:
            ind_medians[ind] = np.median(rets)

    # Assign: each stock gets its industry's median momentum
    scores = {}
    for code in codes:
        ind = industry_map.get(code, "未知")
        if ind in ind_medians:
            scores[code] = ind_medians[ind]

    return scores


def screen(date_str: str = None, top_n: int = 200) -> pd.DataFrame:
    """
    主筛选函数。

    Args:
        date_str: 日期 "YYYYMMDD"，默认最新交易日
        top_n: 输出前 N 只股票

    Returns:
        DataFrame with columns:
        code, name, industry, sector(景气度), moat(壁垒), valuation(估值),
        composite_score, flags(标签)
    """
    if date_str is None:
        # 取最新调仓日
        import datetime
        today = datetime.date.today().strftime("%Y%m%d")
        cal = get_trade_calendar("20240101", today)
        if len(cal) == 0:
            date_str = today
        else:
            date_str = cal["trade_date"].iloc[-1]

    t_date = get_t_date(date_str)
    logger.info(f"筛选日期: {date_str}, 数据截止: {t_date}")

    # 1. 获取股票池 + 估值排雷
    universe_df = get_universe(t_date)
    codes_all = universe_df["code"].tolist()
    logger.info(f"全市场: {len(codes_all)} 只")

    filtered = apply_valuation_filter(t_date, codes_all)
    logger.info(f"估值排雷后: {len(filtered)} 只")

    # 2. 行业映射
    industry_map = get_sw_industry()

    # 3. 信号计算
    logger.info("计算信号...")
    rps_scores = compute_rps60(filtered, t_date, industry_map)
    ind_scores = compute_industry_momentum(filtered, t_date, industry_map)
    s5 = compute_S5(t_date, filtered, industry_map)
    s7 = compute_S7(t_date, filtered, industry_map)

    # 4. 构建评分
    results = []
    for code in filtered:
        name = universe_df[universe_df["code"] == code]["name"].values
        name = name[0] if len(name) > 0 else ""

        # 简化版景气度：RPS60(0-100) + 行业动量(连续值)
        rps = rps_scores.get(code, 50)      # 50 = 中位
        ind_mom = ind_scores.get(code, 0)

        # 将 RPS 标准化到 ~Z-score 范围
        rps_z = (rps - 50) / 20
        ind_z = ind_mom / 0.15  # 约 15% 标准差

        s5_val = s5.get(code, np.nan) if code in s5.index else np.nan
        s7_val = s7.get(code, np.nan) if code in s7.index else np.nan

        # 景气度 = RPS + 行业动量
        momentum = rps_z * 0.6 + ind_z * 0.4

        # 壁垒 = S5 + S7，NaN→0
        moat_vals = [v for v in [s5_val, s7_val] if not np.isnan(v)]
        moat = np.mean(moat_vals) if moat_vals else 0.0

        # 估值 = 距200日均线距离的逆向指标（离均线越近越便宜，越远越贵）
        df = _load_price_data(code)
        valuation = 0.0
        if len(df) >= 200:
            close = df["close"]
            ma200 = close.rolling(200).mean().iloc[-1]
            if ma200 > 0:
                dev = abs(close.iloc[-1] - ma200) / ma200
                valuation = min(2.0, (1.0 - dev / 0.8))  # 距MA200<80%=正面，>80%=负面

        results.append({
            "code": code,
            "name": name,
            "industry": industry_map.get(code, ""),
            "RPS60": round(rps, 1),
            "ind_momentum": round(ind_mom * 100, 1),
            "S5": round(s5_val, 3) if not np.isnan(s5_val) else 0.0,
            "S7": round(s7_val, 3) if not np.isnan(s7_val) else 0.0,
            "momentum": round(momentum, 3),
            "moat": round(moat, 3),
            "valuation": round(valuation, 3),
        })

    df = pd.DataFrame(results)

    # 5. Regime 判定 + 动态权重
    regime_result = detect_regime(t_date)
    r = regime_result.regime
    if r == "BULL":
        w_m, w_b, w_v = 0.50, 0.30, 0.20  # 景气度>壁垒>估值
    elif r == "BEAR":
        w_m, w_b, w_v = 0.20, 0.30, 0.50  # 估值>壁垒>景气度
    else:  # STRUCT
        w_m, w_b, w_v = 0.35, 0.35, 0.30  # 均衡

    df["composite"] = (
        df["momentum"] * w_m + df["moat"] * w_b + df["valuation"] * w_v
    )
    df = df.sort_values("composite", ascending=False).head(top_n)

    logger.info(f"当前市场状态: {r} → 权重: 景气度={w_m} 壁垒={w_b} 估值={w_v}")
    logger.info(f"筛选完成: {len(df)} 只")
    logger.info(f"按框架: 牛市→景气度优先, 熊市→估值优先, 结构市→均衡")

    # 6. 添加定性标签
    df["momentum_level"] = pd.cut(df["momentum"],
        bins=[-99, -0.3, 0.3, 99], labels=["弱", "中", "强"])
    df["moat_level"] = pd.cut(df["moat"],
        bins=[-99, -0.3, 0.3, 99], labels=["低", "中", "高"])

    return df


def main():
    df = screen()
    out_path = "output/screener_results.csv"
    os.makedirs("output", exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n已保存: {out_path}")
    print(f"\nTop 20:")
    print(df.head(20)[["code", "name", "industry", "RPS60", "ind_momentum", "momentum_level", "moat_level", "composite"]].to_string(index=False))
    return df


if __name__ == "__main__":
    main()
