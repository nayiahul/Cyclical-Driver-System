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
from signals import compute_S1, compute_S2, compute_S5, compute_S7, _load_price_data
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
    s1 = compute_S1(t_date, filtered, industry_map)
    s2 = compute_S2(t_date, filtered, industry_map)
    s5 = compute_S5(t_date, filtered, industry_map)
    s7 = compute_S7(t_date, filtered, industry_map)

    # PE估值: 收盘价 / 最新年报EPS, 行业内排名
    fin = pd.read_csv("data/cache/tdx_financials.csv", dtype={"code": str, "report_date_str": str})
    fin_annual = fin[fin["report_date_str"].str[4:6] == "12"].copy()
    fin_annual = fin_annual.sort_values("report_date_str").groupby("code").last()
    fin_annual["pe_proxy"] = np.where(
        fin_annual["eps"] > 0.01,
        fin_annual["eps"].clip(lower=0.01), np.nan
    )

    # 4. 构建评分
    results = []
    for code in filtered:
        name = universe_df[universe_df["code"] == code]["name"].values
        name = name[0] if len(name) > 0 else ""

        # --- 景气度(4子因子) ---
        rps = rps_scores.get(code, 50)
        ind_mom = ind_scores.get(code, 0)
        s1_val = s1.get(code, np.nan) if code in s1.index else np.nan
        s2_val = s2.get(code, np.nan) if code in s2.index else np.nan

        rps_z = (rps - 50) / 20
        ind_z = ind_mom / 0.15
        s1_z = s1_val if not np.isnan(s1_val) else 0.0
        s2_z = s2_val if not np.isnan(s2_val) else 0.0
        s1_z = max(-3.0, min(3.0, s1_z))
        s2_z = max(-3.0, min(3.0, s2_z))

        # S1/S2均有效时→4子因子等权；否则→RPS+行业动量
        if not np.isnan(s1_val) and not np.isnan(s2_val):
            momentum = rps_z * 0.25 + ind_z * 0.15 + s1_z * 0.30 + s2_z * 0.30
        else:
            momentum = rps_z * 0.6 + ind_z * 0.4

        # --- 壁垒 ---
        s5_val = s5.get(code, np.nan) if code in s5.index else np.nan
        s7_val = s7.get(code, np.nan) if code in s7.index else np.nan
        if not np.isnan(s5_val): s5_val = max(-3.0, min(3.0, s5_val))
        if not np.isnan(s7_val): s7_val = max(-3.0, min(3.0, s7_val))
        moat_vals = [v for v in [s5_val, s7_val] if not np.isnan(v)]
        moat = np.mean(moat_vals) if moat_vals else 0.0

        # --- 估值: PE行业内分位 ---
        eps_val = fin_annual.loc[code, "eps"] if code in fin_annual.index else np.nan
        df_price = _load_price_data(code)
        close_price = float(df_price["close"].iloc[-1]) if len(df_price) > 0 else np.nan
        pe_val = close_price / eps_val if (not np.isnan(eps_val) and eps_val > 0.01) else np.nan
        pe_val = min(200, max(1, pe_val)) if not np.isnan(pe_val) else np.nan

        # 行业内PE排名 (lower PE = cheaper = higher score)
        ind_codes = [c for c in filtered if industry_map.get(c) == industry_map.get(code)]
        ind_pes = []
        for c in ind_codes:
            e = fin_annual.loc[c, "eps"] if c in fin_annual.index else np.nan
            cp_df = _load_price_data(c)
            cp = float(cp_df["close"].iloc[-1]) if len(cp_df) > 0 else np.nan
            if not np.isnan(e) and e > 0.01 and not np.isnan(cp):
                p = min(200, max(1, cp / e))
                ind_pes.append(p)
        if not np.isnan(pe_val) and len(ind_pes) >= 5:
            pct = sum(1 for p in ind_pes if p >= pe_val) / len(ind_pes)
            valuation = (pct - 0.5) * 4  # centile → Z-score range
        else:
            valuation = 0.0

        # --- 技术温度(仅观察) ---
        tech_temp = 0.0
        if len(df_price) >= 200:
            close = df_price["close"]
            ma200 = close.rolling(200).mean().iloc[-1]
            if ma200 > 0:
                dev = (close.iloc[-1] - ma200) / ma200
                tech_temp = round(dev * 100, 1)

        results.append({
            "code": code,
            "name": name,
            "industry": industry_map.get(code, ""),
            "RPS60": round(rps, 1),
            "ind_momentum": round(ind_mom * 100, 1),
            "S1": round(s1_z, 3),
            "S2": round(s2_z, 3),
            "S5": round(s5_val, 3) if not np.isnan(s5_val) else 0.0,
            "S7": round(s7_val, 3) if not np.isnan(s7_val) else 0.0,
            "PE": round(pe_val, 1) if not np.isnan(pe_val) else 0.0,
            "momentum": round(momentum, 3),
            "moat": round(moat, 3),
            "valuation": round(valuation, 3),
            "tech_temp": tech_temp,
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


def screen_growth(date_str: str = None, top_n: int = 50) -> pd.DataFrame:
    """
    景气成长模式：筛选具备中线爆发潜力的标的。

    条件: RPS60≥80, PE<60, 壁垒不差(moat>-0.5)
    权重: 景气度60% + S1/S2(基本面催化)30% + 壁垒10%
    """
    df_all = screen(date_str, top_n=500)  # 先跑全景
    # 过滤条件
    df = df_all[
        (df_all["RPS60"] >= 80) &
        (df_all["PE"] < 60) &
        (df_all["moat"] > -0.5) &
        (df_all["PE"] > 0)
    ].copy()

    if len(df) == 0:
        logger.warning("无符合成长筛选条件的标的，放宽条件...")
        df = df_all[(df_all["RPS60"] >= 70) & (df_all["moat"] > -1.0)].copy()

    # S1/S2 催化得分
    df["catalyst"] = df[["S1", "S2"]].max(axis=1)  # 取最强的那个
    df["catalyst"] = df["catalyst"].clip(-2, 3)

    # 景气成长综合得分
    df["growth_score"] = (
        df["momentum"] * 0.4 +
        df["catalyst"] * 0.3 +
        (df["RPS60"] / 100) * 0.2 +
        df["moat"] * 0.1
    )
    df = df.sort_values("growth_score", ascending=False).head(top_n)

    # 添加催化剂标签
    def _tag(row):
        tags = []
        if row["S1"] > 0.5: tags.append("利润加速↑")
        if row["S2"] > 0.5: tags.append("产能扩张↑")
        if row["RPS60"] >= 95: tags.append("动量极强")
        if row["PE"] < 20: tags.append("低估值")
        return " | ".join(tags) if tags else "—"

    df["catalyst_tags"] = df.apply(_tag, axis=1)
    df["growth_score"] = df["growth_score"].round(4)

    return df


def main():
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "default"

    if mode == "growth":
        df = screen_growth()
        out_path = "output/screener_growth.csv"
        os.makedirs("output", exist_ok=True)
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"\n已保存: {out_path}")
        print(f"\nTop 20 (景气成长):")
        print(df.head(20)[["code", "name", "industry", "RPS60", "PE",
              "catalyst_tags", "growth_score"]].to_string(index=False))
        return

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
