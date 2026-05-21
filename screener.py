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
from config.strategic_industries import get_strategic_tags, get_strategic_bonus
from data_governance import filter_available_reports
from industry import get_sw_industry_l3


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


def _apply_industry_constraint(scores: dict[str, float],
                                industry_map: dict, regime: str,
                                top_n: int) -> dict[str, float]:
    """
    Regime 自适应行业暴露约束。

    BULL≤25%, STRUCT≤15%, BEAR≤10%。
    软约束: 超过上限后线性扣分。拥挤度惩罚: >20%→×0.85。
    """
    limits = {"BULL": 0.25, "STRUCT": 0.15, "BEAR": 0.10}
    cap = limits.get(regime, 0.15)

    # 初次排序取 top_n，检测行业分布
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_codes = [c for c, _ in ranked[:top_n]]
    ind_counts = {}
    for c in top_codes:
        ind = industry_map.get(c, "未知")
        ind_counts[ind] = ind_counts.get(ind, 0) + 1

    # 对超标行业施加惩罚
    adjusted = {}
    for code, score in scores.items():
        ind = industry_map.get(code, "未知")
        weight = ind_counts.get(ind, 0) / top_n
        penalty = 1.0
        if weight > cap:
            penalty = max(0.60, 1.0 - (weight - cap) * 3.0)  # 线性衰减，下限 0.6
        if weight > 0.20:
            penalty = min(penalty, 0.85)  # 拥挤度惩罚
        adjusted[code] = score * penalty

    return adjusted


def compute_composite(t_date: str, codes: list[str],
                      industry_map: dict, l3_map: dict = None,
                      prev_regime: str = None,
                      bull_streak: int = 0,
                      top_n: int = 200) -> tuple[dict[str, float], str, int]:
    """
    计算主筛选路径的 composite 得分。

    因子集: RPS60 + 行业动量 + S1 + S2 + S5 + S7 + PE
    合成: Regime 动态权重 (BULL/STRUCT/BEAR) + 滞回

    回测引擎和 screen() 共用此函数，确保验证路径与使用路径一致。

    Returns:
        ({code: composite_score}, {code: pure_alpha}, regime, bull_streak)
    """
    # 信号计算
    rps_scores = compute_rps60(codes, t_date, industry_map)
    ind_scores = compute_industry_momentum(codes, t_date, industry_map)
    s1, s1_raw = compute_S1(t_date, codes, industry_map, return_raw=True)
    s2 = compute_S2(t_date, codes, industry_map)
    s5 = compute_S5(t_date, codes, industry_map)
    s7 = compute_S7(t_date, codes, industry_map)

    # PE TTM: 近4季单季度EPS之和
    fin = pd.read_csv("data/cache/tdx_financials.csv", dtype={"code": str, "report_date_str": str})
    fin = filter_available_reports(fin, t_date)
    ttm_eps_map = {}
    for code in codes:
        cfin = fin[fin["code"] == code].sort_values("report_date_str")
        if len(cfin) < 4: continue
        last4 = cfin.tail(4)
        dq_sum = last4["deducted_profit_q"].sum()
        shares = last4["total_shares"].iloc[-1]
        if shares > 0 and not np.isnan(dq_sum):
            ttm = dq_sum / shares
            if ttm > 0.01: ttm_eps_map[code] = ttm

    ind_pe_map = {}
    for code in codes:
        ind = industry_map.get(code, "未知")
        if ind not in ind_pe_map:
            ind_codes = [c for c in codes if industry_map.get(c) == ind]
            ind_pes = []
            for c in ind_codes:
                e = ttm_eps_map.get(c, np.nan)
                cp_df = _load_price_data(c)
                cp = float(cp_df["close"].iloc[-1]) if len(cp_df) > 0 else np.nan
                if not np.isnan(e) and e > 0.01 and not np.isnan(cp):
                    p = min(200, max(1, cp / e)); ind_pes.append(p)
            ind_pe_map[ind] = ind_pes

    # 逐股评分
    scores = {}
    for code in codes:
        # 景气度
        rps = rps_scores.get(code, 50)
        ind_mom = ind_scores.get(code, 0)
        s1_val = s1.get(code, np.nan) if code in s1.index else np.nan
        s2_val = s2.get(code, np.nan) if code in s2.index else np.nan

        rps_z = (rps - 50) / 20
        ind_z = ind_mom / 0.15
        s1_z = max(-3.0, min(3.0, s1_val if not np.isnan(s1_val) else 0.0))
        s2_z = max(-3.0, min(3.0, s2_val if not np.isnan(s2_val) else 0.0))

        if not np.isnan(s1_val) and not np.isnan(s2_val):
            momentum = rps_z * 0.25 + ind_z * 0.15 + s1_z * 0.30 + s2_z * 0.30
        else:
            momentum = rps_z * 0.6 + ind_z * 0.4

        # 壁垒
        s5_val = s5.get(code, np.nan) if code in s5.index else np.nan
        s7_val = s7.get(code, np.nan) if code in s7.index else np.nan
        if not np.isnan(s5_val): s5_val = max(-3.0, min(3.0, s5_val))
        if not np.isnan(s7_val): s7_val = max(-3.0, min(3.0, s7_val))
        moat_vals = [v for v in [s5_val, s7_val] if not np.isnan(v)]
        moat = np.mean(moat_vals) if moat_vals else 0.0

        # 估值: PE行业内分位 (TTM EPS)
        eps_val = ttm_eps_map.get(code, np.nan)
        df_price = _load_price_data(code)
        close_price = float(df_price["close"].iloc[-1]) if len(df_price) > 0 else np.nan
        pe_val = close_price / eps_val if (not np.isnan(eps_val) and eps_val > 0.01) else np.nan
        pe_val = min(200, max(1, pe_val)) if not np.isnan(pe_val) else np.nan
        ind_pes = ind_pe_map.get(industry_map.get(code, ""), [])
        if not np.isnan(pe_val) and len(ind_pes) >= 5:
            pct = sum(1 for p in ind_pes if p >= pe_val) / len(ind_pes)
            valuation = (pct - 0.5) * 4
        else:
            valuation = 0.0
        val_ratio = pe_val

        scores[code] = (momentum, moat, valuation)

    # Regime 动态权重 + 滞回
    regime_result = detect_regime(t_date, prev_regime=prev_regime,
                                  bull_streak=bull_streak)
    r = regime_result.regime
    new_streak = regime_result.bull_streak
    if r == "BULL":
        w_m, w_b, w_v = 0.50, 0.30, 0.20
    elif r == "BEAR":
        w_m, w_b, w_v = 0.20, 0.30, 0.50
    else:
        w_m, w_b, w_v = 0.35, 0.35, 0.30

    # 风格 Regime 仅诊断 (基于 PE 趋势, 不参与权重)
    pe_change = float(regime_result.details.get("pe_60d_change", 0) or 0)
    from regime.style import detect_style
    style = detect_style(pe_change)

    composite = {}
    for code, (m, b, v) in scores.items():
        composite[code] = m * w_m + b * w_b + v * w_v

    # 纯 alpha: 剥除行业均值
    ind_avg = {}
    ind_scores = defaultdict(list)
    for code, score in composite.items():
        ind = industry_map.get(code, "未知")
        ind_scores[ind].append(score)
    for ind, scores_list in ind_scores.items():
        avg = sum(scores_list) / len(scores_list)
        ind_avg[ind] = avg

    pure_alpha = {
        code: score - ind_avg.get(industry_map.get(code, "未知"), 0)
        for code, score in composite.items()
    }

    # 行业暴露约束 (对 composite 施加)
    composite = _apply_industry_constraint(composite, industry_map, r, top_n)
    # pure_alpha 也同步约束
    pure_alpha = _apply_industry_constraint(pure_alpha, industry_map, r, top_n)

    return composite, pure_alpha, r, new_streak


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

    industry_map = get_sw_industry()
    l3_map = get_sw_industry_l3()
    filtered = apply_valuation_filter(t_date, codes_all, industry_map)
    logger.info(f"估值排雷后: {len(filtered)} 只")

    # 3. 信号计算
    logger.info("计算信号...")
    rps_scores = compute_rps60(filtered, t_date, industry_map)
    ind_scores = compute_industry_momentum(filtered, t_date, industry_map)
    s1, s1_raw = compute_S1(t_date, filtered, industry_map, return_raw=True)
    s2 = compute_S2(t_date, filtered, industry_map)
    s5 = compute_S5(t_date, filtered, industry_map)
    s7 = compute_S7(t_date, filtered, industry_map)

    # PE TTM: 近4季单季度EPS之和
    fin = pd.read_csv("data/cache/tdx_financials.csv", dtype={"code": str, "report_date_str": str})
    fin = filter_available_reports(fin, t_date)
    ttm_eps_map = {}
    for code in filtered:
        cfin = fin[fin["code"] == code].sort_values("report_date_str")
        if len(cfin) < 4: continue
        last4 = cfin.tail(4)
        dq_sum = last4["deducted_profit_q"].sum()
        shares = last4["total_shares"].iloc[-1]
        if shares > 0 and not np.isnan(dq_sum):
            ttm = dq_sum / shares
            if ttm > 0.01: ttm_eps_map[code] = ttm

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
        s1_raw_val = s1_raw.get(code, np.nan) if code in s1_raw.index else np.nan
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

        # --- 估值: PE行业内分位 (TTM EPS) ---
        eps_val = ttm_eps_map.get(code, np.nan)
        df_price = _load_price_data(code)
        close_price = float(df_price["close"].iloc[-1]) if len(df_price) > 0 else np.nan
        pe_val = close_price / eps_val if (not np.isnan(eps_val) and eps_val > 0.01) else np.nan
        pe_val = min(200, max(1, pe_val)) if not np.isnan(pe_val) else np.nan
        ind_codes = [c for c in filtered if industry_map.get(c) == industry_map.get(code)]
        ind_pes = []
        for c in ind_codes:
            e = ttm_eps_map.get(c, np.nan)
            cp_df = _load_price_data(c)
            cp = float(cp_df["close"].iloc[-1]) if len(cp_df) > 0 else np.nan
            if not np.isnan(e) and e > 0.01 and not np.isnan(cp):
                p = min(200, max(1, cp / e)); ind_pes.append(p)
        if not np.isnan(pe_val) and len(ind_pes) >= 5:
            pct = sum(1 for p in ind_pes if p >= pe_val) / len(ind_pes)
            valuation = (pct - 0.5) * 4
        else:
            valuation = 0.0
        val_ratio = pe_val

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
            "sw3_name": l3_map.get(code, ""),
            "strategic_tags": "|".join(get_strategic_tags(l3_map.get(code, ""))),
            "RPS60": round(rps, 1),
            "ind_momentum": round(ind_mom * 100, 1),
            "S1": round(s1_z, 3),
            "S1_raw": round(s1_raw_val, 1) if not np.isnan(s1_raw_val) else 0.0,
            "S2": round(s2_z, 3),
            "S5": round(s5_val, 3) if not np.isnan(s5_val) else 0.0,
            "S7": round(s7_val, 3) if not np.isnan(s7_val) else 0.0,
            "val_ratio": round(val_ratio, 1) if not np.isnan(val_ratio) else 0.0,
            "momentum": round(momentum, 3),
            "moat": round(moat, 3),
            "valuation": round(valuation, 3),
            "tech_temp": tech_temp,
        })

    df = pd.DataFrame(results)

    # 5. Regime 判定 + 动态权重 (单次调用，不跟踪状态)
    regime_result = detect_regime(t_date)
    r = regime_result.regime
    if r == "BULL":
        w_m, w_b, w_v = 0.50, 0.30, 0.20  # 景气度>壁垒>估值
    elif r == "BEAR":
        w_m, w_b, w_v = 0.20, 0.30, 0.50  # 估值>壁垒>景气度
    else:  # STRUCT
        w_m, w_b, w_v = 0.35, 0.35, 0.30  # 均衡

    # 风格 Regime 仅诊断 (不参与权重)
    pe_change = float(regime_result.details.get("pe_60d_change", 0) or 0)
    from regime.style import detect_style
    style = detect_style(pe_change)

    df["composite"] = (
        df["momentum"] * w_m + df["moat"] * w_b + df["valuation"] * w_v
    )

    # 行业暴露约束: 先取 top_n 检测分布，再对超标行业施加惩罚
    scores = dict(zip(df["code"], df["composite"]))
    constrained = _apply_industry_constraint(scores, industry_map, r, top_n)
    df["composite"] = df["code"].map(constrained)

    df = df.sort_values("composite", ascending=False).head(top_n)

    logger.info(f"当前市场状态: {r}({style}) → 权重: 景气度={w_m:.2f} 壁垒={w_b:.2f} 估值={w_v:.2f}")
    logger.info(f"筛选完成: {len(df)} 只")
    logger.info(f"按框架: 牛市→景气度优先, 熊市→估值优先, 结构市→均衡")

    # 6. 添加定性标签
    df["momentum_level"] = pd.cut(df["momentum"],
        bins=[-99, -0.3, 0.3, 99], labels=["弱", "中", "强"])
    df["moat_level"] = pd.cut(df["moat"],
        bins=[-99, -0.3, 0.3, 99], labels=["低", "中", "高"])

    # 7. 因子相关性诊断
    from diagnostics.factor_corr import compute_factor_correlation, save_correlation, highlight_concentration
    factor_scores = {
        "RPS60": pd.Series(rps_scores),
        "ind_mom": pd.Series(ind_scores),
        "S1": s1,
        "S2": s2,
        "S5": s5,
        "S7": s7,
        "valuation": pd.Series({c: df[df["code"]==c]["valuation"].values[0]
                                for c in df["code"] if c in df["code"].values}),
    }
    corr = compute_factor_correlation(factor_scores)
    if not corr.empty:
        save_correlation(corr, date_str)
        warnings = highlight_concentration(corr)
        if warnings:
            logger.warning(f"因子高相关: {'; '.join(warnings)}")

    # 8. 纯 alpha: 剥除行业均值后的残差
    ind_avg = df.groupby("industry")["composite"].transform("mean")
    df["pure_alpha"] = (df["composite"] - ind_avg).round(4)

    # 9. 诊断列: 行业暴露 + 流动性 + 数据新鲜度 + 风格标记
    ind_counts = df["industry"].value_counts()
    df["ind_weight_pct"] = df["industry"].map(ind_counts / len(df) * 100).round(1)

    # 流动性分档
    df["liquidity_flag"] = "mid"
    df.loc[df["val_ratio"] < 1.0, "liquidity_flag"] = "large"
    df.loc[df["val_ratio"] > 50, "liquidity_flag"] = "small"

    # 数据新鲜度: 用 t_date 估算 (日线日期即 t_date)
    df["data_date"] = t_date

    # 风格标记
    df["style_hint"] = "blend"
    df.loc[(df["momentum"] > 0.5) & (df["valuation"] < 0), "style_hint"] = "growth"
    df.loc[(df["valuation"] > 1.0), "style_hint"] = "value"

    # v2.0: 自动主题动量 — RPS60 跳升检测
    from diagnostics.themes import detect_hot_themes, save_themes
    themes = detect_hot_themes(rps_scores, industry_map, l3_map)
    hot_themes = themes[themes["is_hot"]]
    if len(hot_themes) > 0:
        save_themes(themes, date_str)
        logger.info(f"热门主题: {len(hot_themes)} 个三级行业 (RPS60中位数>{15})")

    return df


def screen_growth(date_str: str = None, top_n: int = 50) -> pd.DataFrame:
    """
    拐点爆发模式：找基本面正在改善但价格尚未充分反应的标的。

    估值用行业内PE分位替代绝对值，不同行业不直接比PE。
    """
    df_all = screen(date_str, top_n=800)

    # PEG = PE / S1原始yoy增速 (标准公式)
    # growth cap: 50% 上限防止极端值，5% 下限防止 PEG 爆炸
    df_all["growth"] = df_all["S1_raw"].clip(5, 50)
    df_all["PEG"] = np.where(
        (df_all["val_ratio"] > 0) & (df_all["val_ratio"] < 200) & (df_all["S1_raw"] > 0),
        df_all["val_ratio"] / df_all["growth"],
        np.nan
    )
    # 行业内估值合理 = valuation>0（PE在行业后半段→偏便宜）
    # PEG合理 = PEG < 2.5
    df_all["val_ok"] = (df_all["valuation"] > -0.2) | (df_all["PEG"] < 2.5)

    # 过滤：有基本面改善 + 有动量 + 估值得看 + 质量不差
    df = df_all[
        ((df_all["S1"] > 0) | (df_all["S2"] > 0)) &
        (df_all["RPS60"] >= 55) &
        (df_all["val_ratio"] > 0) &
        df_all["val_ok"] &
        (df_all["moat"] > -0.5)
    ].copy()

    if len(df) < 20:
        logger.warning(f"仅 {len(df)} 只，放宽val_ok")
        df = df_all[
            ((df_all["S1"] > 0) | (df_all["S2"] > 0)) &
            (df_all["RPS60"] >= 50) & (df_all["PE"] > 0) &
            (df_all["moat"] > -1.0)
        ].copy()

    # 估值吸引力：valuation(行业内分位) + PEG修正
    df["val_attract"] = df["valuation"].clip(-2, 3) * 0.6
    df.loc[df["PEG"] < 1.5, "val_attract"] += 0.5  # 低PEG加分
    df.loc[df["PEG"] > 3.0, "val_attract"] -= 0.3   # 高PEG减分

    # 基本面催化剂
    df["catalyst"] = df[["S1", "S2"]].max(axis=1).clip(0, 3)

    # 动量空间
    df["room_to_run"] = 1 - abs(df["RPS60"] - 70) / 40
    df["room_to_run"] = df["room_to_run"].clip(0, 1)

    # 国情加成：战略行业额外得分
    df["strategic_bonus"] = df["sw3_name"].apply(lambda x: get_strategic_bonus(x) if isinstance(x, str) else 0)

    # 拐点得分：催化30 + 动量空间20 + 估值吸引力20 + 壁垒15 + 战略加成15
    df["inflection_score"] = (
        df["catalyst"] * 0.30 +
        df["room_to_run"] * 0.20 +
        df["val_attract"] * 0.20 +
        df["moat"] * 0.15 +
        df["strategic_bonus"] * 0.15
    )
    df = df.sort_values("inflection_score", ascending=False).head(top_n)

    def _tag(row):
        tags = []
        if row["S1"] > 0.3: tags.append("利润拐点")
        if row["S2"] > 0.3: tags.append("产能扩张")
        if 55 <= row["RPS60"] <= 75: tags.append("刚启动")
        if 75 < row["RPS60"] <= 90: tags.append("趋势中")
        if row["S1"] > 0 and row["S2"] > 0: tags.append("★双击")
        if row["valuation"] > 1.0: tags.append("低估")
        return " | ".join(tags) if tags else "—"

    df["inflection_tags"] = df.apply(_tag, axis=1)
    df["inflection_score"] = df["inflection_score"].round(4)
    df["PEG"] = df["PEG"].round(1)

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
        print(df.head(20)[["code", "name", "industry", "RPS60", "val_ratio",
              "strategic_tags", "inflection_tags", "inflection_score"]].to_string(index=False))
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
