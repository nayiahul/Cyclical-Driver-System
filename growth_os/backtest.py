"""Growth OS 回测验证 — 多点历史筛选 + 前瞻收益跟踪。

验证逻辑：
  在每个季度末运行五层漏斗筛选，跟踪 Top N 选股池在
  3/6/12 个月的前瞻收益，与沪深300对比。
"""
import os
import sys
import time
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger

warnings.filterwarnings("ignore")

from growth_os.config import DATA_PATHS, EXCLUDED_INDUSTRIES_L1
from growth_os.data import (
    load_growth_data, get_industry, get_price_data, load_tdx_financials,
)
from growth_os.lifecycle import classify_lifecycle
from growth_os.funnel import run_funnel
from growth_os.scorecard import GrowthScorecard, compute_composite
from growth_os.regime import (
    compute_regime, reset_state_machine, RegimeOutput, RegimeState, regime_summary,
)


@dataclass
class BacktestResult:
    """回测结果容器。"""
    screening_dates: list[str]
    top_n: int
    forward_periods: list[int]          # [3, 6, 12] 个月
    pool_returns: pd.DataFrame          # 每期选股池的平均前瞻收益
    benchmark_returns: pd.DataFrame     # 同期基准收益
    hit_rates: dict                     # {period: hit_rate%}
    avg_excess_returns: dict            # {period: avg_excess%}
    calmar_by_period: dict              # {period: calmar}
    max_drawdown_by_period: dict        # {period: max_dd%}
    regime_log: list[dict] = None       # 每期 L0 状态记录


def _get_quarterly_dates(start: str, end: str) -> list[str]:
    """生成季度末交易日列表（月末最后一个自然日近似）。"""
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)
    dates = pd.date_range(start_dt, end_dt, freq="QE")
    return [d.strftime("%Y%m%d") for d in dates]


def _get_benchmark_returns(hold_date: str, forward_months: int,
                           max_lookforward: str) -> float | None:
    """获取沪深300在持有期的收益。

    Args:
        hold_date: 建仓日期 YYYYMMDD
        forward_months: 持有月数
        max_lookforward: 数据截止日

    Returns:
        持有期收益率 (小数), e.g. 0.05 = 5%
    """
    import akshare as ak
    try:
        df = ak.stock_zh_index_daily(symbol="sh000300")
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        t0 = pd.Timestamp(hold_date)
        t1 = t0 + pd.DateOffset(months=forward_months)
        t1 = min(t1, pd.Timestamp(max_lookforward))

        # 找到建仓日和到期日附近的收盘价
        before_start = df[df["date"] <= t0]
        before_end = df[df["date"] <= t1]
        if before_start.empty or before_end.empty:
            return None

        p0 = before_start.iloc[-1]["close"]
        p1 = before_end.iloc[-1]["close"]
        return float(p1 / p0 - 1)
    except Exception:
        return None


def _get_forward_return(code: str, hold_date: str, forward_months: int,
                        max_lookforward: str) -> float | None:
    """获取单只股票的持有期收益。

    Args:
        code: 股票代码
        hold_date: 建仓日期 YYYYMMDD
        forward_months: 持有月数
        max_lookforward: 数据截止日

    Returns:
        持有期收益率 (小数), 或 None
    """
    price_df = get_price_data(code)
    if price_df is None:
        return None

    price_df = price_df.sort_values("date")
    t0 = pd.Timestamp(hold_date)
    t1 = t0 + pd.DateOffset(months=forward_months)
    t1 = min(t1, pd.Timestamp(max_lookforward))

    before_start = price_df[price_df["date"] <= t0]
    before_end = price_df[price_df["date"] <= t1]
    if before_start.empty or before_end.empty:
        return None

    p0 = before_start.iloc[-1]["close"]
    p1 = before_end.iloc[-1]["close"]
    if p0 <= 0:
        return None
    return float(p1 / p0 - 1)


def _compute_calmar(returns: list[float]) -> float:
    """从收益序列计算 Calmar 比率。

    Calmar = 年化收益 / |最大回撤|
    """
    if not returns or len(returns) < 2:
        return 0.0

    cum = np.cumprod([1 + r for r in returns])
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    max_dd = abs(dd.min())

    if max_dd < 0.001:
        return 0.0

    total_return = cum[-1] - 1
    n_periods = len(returns)
    ann_return = (1 + total_return) ** (12 / n_periods) - 1 if n_periods > 0 else 0

    return round(ann_return / max_dd, 2)


def run_backtest(
    start_date: str = "20220101",
    end_date: str = "20260501",
    top_n: int = 30,
    forward_periods: list[int] = None,
    min_market_cap: float = 50.0,
    pool_size: int = 800,
    use_regime: bool = True,
) -> BacktestResult:
    """运行 Growth OS 多点历史回测。

    Args:
        start_date: 回测起始日 YYYYMMDD
        end_date: 回测结束日 YYYYMMDD
        top_n: 每期选股数量（use_regime=True 时被 L0 动态覆盖）
        forward_periods: 前瞻收益期数(月), 默认 [3, 6, 12]
        min_market_cap: 最低市值(亿元)
        pool_size: 每期候选池大小
        use_regime: 是否启用 L0 风格择时门控

    Returns:
        BacktestResult
    """
    if forward_periods is None:
        forward_periods = [3, 6, 12]

    # L0 状态机重置
    if use_regime:
        reset_state_machine()

    screening_dates = _get_quarterly_dates(start_date, end_date)
    # 过滤掉太近的日期（前瞻期不足）
    max_forward = max(forward_periods)
    cutoff = pd.Timestamp(end_date) - pd.DateOffset(months=max_forward)
    screening_dates = [d for d in screening_dates
                       if pd.Timestamp(d) <= cutoff]

    logger.info(f"回测: {len(screening_dates)} 个季度筛选点, "
                f"Top{top_n}, 前瞻{forward_periods}个月"
                f"{', L0风格择时: 启用' if use_regime else ''}")

    pool_returns_records = []
    benchmark_records = []
    regime_log = []

    for i, t_date in enumerate(screening_dates):
        # L0 风格择时
        regime = compute_regime(t_date) if use_regime else None
        if regime:
            l1_strict = regime.l1_strict
            w_mode = regime.weight_mode
            g_discount = regime.g_proxy_discount
            is_defense = regime.state.value == "DEFENSE"
            is_recovery = regime.state.value == "RECOVERY"
        else:
            l1_strict = False
            w_mode = "lifecycle"
            g_discount = 1.0
            is_defense = False

        if regime:
            logger.info(f"[{i+1}/{len(screening_dates)}] 筛选日期: {t_date} "
                        f"| Regime: {regime.state.value} "
                        f"{'→防御资产' if is_defense else '→55/45混合' if is_recovery else 'wmode=' + w_mode}")
        else:
            logger.info(f"[{i+1}/{len(screening_dates)}] 筛选日期: {t_date}")

        # 记录 L0 状态
        if regime:
            regime_log.append({
                "screening_date": t_date,
                "regime_state": regime.state.value,
                "weight_mode": w_mode,
                "is_defense_assets": is_defense,
                "is_recovery": is_recovery,
                **{f"ch_{k}": v["triggered"]
                   for k, v in regime.channel_signals.items()},
            })

        try:
            # ---- 加载数据 + 运行漏斗（所有模式都跑，DEFENSE时作反事实） ----
            df = load_growth_data(t_date)
            df = df[df["market_cap"] >= min_market_cap]
            if len(df) > pool_size:
                df = df.nlargest(pool_size, "market_cap")
            codes = df["code"].tolist()

            funnel_returns: dict[int, float | None] = {}
            if codes:
                results = []
                for code in codes:
                    try:
                        ind = get_industry(code)
                        lc, lc_reason = classify_lifecycle(code, t_date, ind)
                        funnel = run_funnel(code, t_date, ind, lc, l1_strict=l1_strict)
                        if g_discount < 1.0 and not np.isnan(funnel.get("score_l5", np.nan)):
                            funnel["score_l5"] = round(funnel["score_l5"] * g_discount, 1)
                        card = GrowthScorecard(
                            code=code, name=code,
                            industry_l3=ind, industry_l1="",
                            lifecycle=lc, lifecycle_reason=lc_reason,
                            pass_l1=funnel["pass_l1"],
                            l1_red_flags=funnel["l1_red_flags"],
                            score_l2=funnel.get("score_l2", np.nan),
                            score_l3=funnel.get("score_l3", np.nan),
                            score_l4=funnel.get("score_l4", np.nan),
                            score_l5=funnel.get("score_l5", np.nan),
                        )
                        card = compute_composite(card, funnel, weight_mode=w_mode)
                        results.append(card.to_dict())
                    except Exception:
                        continue

                if results:
                    df_result = pd.DataFrame(results)
                    df_result = df_result.sort_values(
                        "composite_score", ascending=False).head(top_n)
                    top_codes = df_result["code"].tolist()
                    for period in forward_periods:
                        fwd_returns = []
                        for code in top_codes:
                            ret = _get_forward_return(code, t_date, period, end_date)
                            if ret is not None:
                                fwd_returns.append(ret)
                        if fwd_returns:
                            funnel_returns[period] = float(np.mean(fwd_returns) * 100)
                        else:
                            funnel_returns[period] = None

            # ---- DEFENSE / RECOVERY 时计算防御资产收益 ----
            defense_rets: dict[int, float] = {}
            if is_defense or is_recovery:
                from growth_os.defense import get_defense_basket_return
                for period in forward_periods:
                    defense_rets[period] = (
                        get_defense_basket_return(t_date, period, end_date) * 100)

            # ---- 记录结果（含归因字段） ----
            for period in forward_periods:
                if is_defense:
                    actual_ret = defense_rets.get(period, 0)
                    cf_ret = funnel_returns.get(period)
                    n = 0
                elif is_recovery:
                    growth_ret = funnel_returns.get(period)
                    def_ret = defense_rets.get(period, 0)
                    if growth_ret is not None:
                        actual_ret = 0.55 * growth_ret + 0.45 * def_ret
                    else:
                        actual_ret = def_ret
                    cf_ret = growth_ret
                    n = 15  # Top15
                else:
                    actual_ret = funnel_returns.get(period)
                    cf_ret = None
                    n = top_n

                hit = 100.0 if actual_ret is not None and actual_ret > 0 else 0.0
                pool_returns_records.append({
                    "screening_date": t_date,
                    "period_months": period,
                    "n_stocks": n,
                    "avg_return": round(actual_ret, 2) if actual_ret is not None else np.nan,
                    "median_return": round(actual_ret, 2) if actual_ret is not None else np.nan,
                    "hit_rate": round(hit, 1),
                    "funnel_cf_return": round(cf_ret, 2) if cf_ret is not None else np.nan,
                    "regime": regime.state.value if regime else "GROWTH_OK",
                })
                bench_ret = _get_benchmark_returns(t_date, period, end_date)
                benchmark_records.append({
                    "screening_date": t_date,
                    "period_months": period,
                    "benchmark_return": round(bench_ret * 100, 2) if bench_ret else np.nan,
                })

        except Exception as e:
            logger.warning(f"筛选日期 {t_date} 失败: {e}")
            continue

    pool_df = pd.DataFrame(pool_returns_records)
    bench_df = pd.DataFrame(benchmark_records)

    # ---- 汇总统计 ----
    hit_rates = {}
    avg_excess = {}
    calmar_by_period = {}
    dd_by_period = {}

    for period in forward_periods:
        period_pool = pool_df[pool_df["period_months"] == period]
        period_bench = bench_df[bench_df["period_months"] == period]

        if period_pool.empty:
            continue

        # 命中率
        hit_rates[period] = round(period_pool["hit_rate"].mean(), 1)

        # 超额收益
        merged = period_pool.merge(period_bench, on="screening_date", how="left")
        merged["excess"] = merged["avg_return"] - merged["benchmark_return"]
        avg_excess[period] = round(merged["excess"].mean(), 2)

        # Calmar (基于每期的平均收益序列)
        returns = [r / 100 for r in merged["avg_return"].dropna().tolist()]
        calmar_by_period[period] = _compute_calmar(returns)

        # 最大回撤
        if returns and len(returns) > 1:
            cum = np.cumprod([1 + r for r in returns])
            peak = np.maximum.accumulate(cum)
            dd = (cum - peak) / peak
            dd_by_period[period] = round(abs(dd.min()) * 100, 1)
        else:
            dd_by_period[period] = 0.0

    return BacktestResult(
        screening_dates=screening_dates,
        top_n=top_n,
        forward_periods=forward_periods,
        pool_returns=pool_df,
        benchmark_returns=bench_df,
        hit_rates=hit_rates,
        avg_excess_returns=avg_excess,
        calmar_by_period=calmar_by_period,
        max_drawdown_by_period=dd_by_period,
        regime_log=regime_log if use_regime else None,
    )


def _alpha_purity_analysis(pool_df: pd.DataFrame, bench_df: pd.DataFrame) -> dict:
    """Alpha 纯度归因。

    用 创业板指日收益-上证50日收益 作为成长因子代理，
    回归策略超额 ~ α + β × 成长因子。
    """
    if pool_df.empty or bench_df.empty:
        return {}

    # 按年度分组
    pool_df = pool_df.copy()
    pool_df["year"] = pd.to_datetime(pool_df["screening_date"], format="%Y%m%d").dt.year

    annual = {}
    for period in [6, 12]:
        pp = pool_df[pool_df["period_months"] == period]
        if pp.empty:
            continue

        by_year = pp.groupby("year")["avg_return"].agg(["mean", "std", "count"])
        annual[period] = {
            year: {
                "avg_return": round(row["mean"], 1),
                "std": round(row["std"], 1),
                "count": int(row["count"]),
            }
            for year, row in by_year.iterrows()
        }

    return {"annual_breakdown": annual}


def compute_attribution(pool_df: pd.DataFrame, bench_df: pd.DataFrame) -> dict:
    """归因分析：拆解超额收益来源。

    返回:
        { "regime_contribution": float,    # DEFENSE切换贡献(pp)
          "stock_alpha": float,            # 漏斗选股贡献(pp)
          "defense_carry": float,          # 防御资产Beta收益(pp)
          "by_period": list[dict],         # 逐期明细
        }
    """
    merged = pool_df.merge(bench_df, on=["screening_date", "period_months"], how="left")
    if "regime" not in merged.columns or merged["regime"].isna().all():
        merged["regime"] = "GROWTH_OK"

    # 筛选12M数据做主要归因
    period = 12
    p12 = merged[merged["period_months"] == period].copy()
    if p12.empty:
        period = max(merged["period_months"].unique())
        p12 = merged[merged["period_months"] == period].copy()

    p12["actual_ret"] = p12["avg_return"]
    p12["bench_ret"] = p12["benchmark_return"]
    p12["cf_ret"] = p12.get("funnel_cf_return", np.nan)
    p12["excess"] = p12["actual_ret"] - p12["bench_ret"]

    regime_contrib = 0.0
    stock_alpha_total = 0.0
    defense_carry_total = 0.0
    details = []

    for _, row in p12.iterrows():
        regime = row["regime"]
        actual = row["actual_ret"]
        bench = row["bench_ret"]
        cf = row["cf_ret"]

        if regime == "DEFENSE":
            # 反事实：假设不切换，漏斗会赚多少
            if not pd.isna(cf):
                rc = actual - cf  # regime contribution
            else:
                rc = actual - bench
            sc = 0.0
            dc = actual - bench  # defense carry = defense vs benchmark
        else:
            rc = 0.0
            sc = actual - bench if not pd.isna(actual) else 0.0
            dc = 0.0

        regime_contrib += rc if not pd.isna(rc) else 0
        stock_alpha_total += sc if not pd.isna(sc) else 0
        defense_carry_total += dc if not pd.isna(dc) else 0

        details.append({
            "screening_date": row["screening_date"],
            "regime": regime,
            "actual": round(actual, 1) if not pd.isna(actual) else 0,
            "bench": round(bench, 1) if not pd.isna(bench) else 0,
            "funnel_cf": round(cf, 1) if not pd.isna(cf) else None,
            "regime_contrib": round(rc, 1) if not pd.isna(rc) else 0,
            "stock_alpha": round(sc, 1) if not pd.isna(sc) else 0,
            "defense_carry": round(dc, 1) if not pd.isna(dc) else 0,
        })

    n = len(p12)
    total_excess = p12["excess"].sum()

    return {
        "period_months": period,
        "n_periods": n,
        "total_excess": round(total_excess, 1),
        "avg_excess_per_period": round(total_excess / n, 1) if n > 0 else 0,
        "regime_contribution": round(regime_contrib, 1),
        "regime_pct": round(regime_contrib / total_excess * 100, 1) if total_excess != 0 else 0,
        "stock_alpha": round(stock_alpha_total, 1),
        "stock_alpha_pct": round(stock_alpha_total / total_excess * 100, 1) if total_excess != 0 else 0,
        "defense_carry": round(defense_carry_total, 1),
        "by_period": details,
    }


def print_attribution_report(attr: dict):
    """打印归因报告。"""
    print(f"\n{'='*70}")
    print(f"  超额收益归因分析（{attr['period_months']}个月前瞻，{attr['n_periods']}期）")
    print(f"{'='*70}")
    print(f"  总超额: {attr['total_excess']:+.1f}pp (均{attr['avg_excess_per_period']:+.1f}pp/期)")
    print()
    print(f"  {'来源':<20} {'贡献':>10} {'占比':>10}")
    print(f"  {'-'*40}")
    print(f"  {'Regime择时(防御切换)':<20} {attr['regime_contribution']:>+9.1f}pp {attr['regime_pct']:>9.1f}%")
    print(f"  {'漏斗选股Alpha':<20} {attr['stock_alpha']:>+9.1f}pp {attr['stock_alpha_pct']:>9.1f}%")
    print(f"  {'防御资产Beta':<20} {attr['defense_carry']:>+9.1f}pp")
    print()
    print(f"  --- 逐期明细 ---")
    print(f"  {'日期':<12} {'Regime':<12} {'实际':>8} {'基准':>8} {'漏斗CF':>8} {'择时贡献':>10} {'选股Alpha':>10}")
    print(f"  {'-'*80}")
    for d in attr["by_period"]:
        print(f"  {d['screening_date']:<12} {d['regime']:<12} "
              f"{d['actual']:>+7.1f}% {d['bench']:>+7.1f}% "
              f"{d['funnel_cf'] if d['funnel_cf'] else 'N/A':>8} "
              f"{d['regime_contrib']:>+9.1f}pp {d['stock_alpha']:>+9.1f}pp")
    print(f"{'='*70}\n")


def print_backtest_report(result: BacktestResult):
    """打印回测报告。"""
    print(f"\n{'='*70}")
    print(f"  Growth OS 回测验证报告")
    print(f"{'='*70}")
    print(f"  筛选期数: {len(result.screening_dates)} 个季度")
    print(f"  每期选股: Top {result.top_n}")
    print(f"  前瞻周期: {result.forward_periods} 个月")
    print(f"{'='*70}")

    print(f"\n{'周期':<10} {'命中率':<10} {'超额收益':<12} {'Calmar':<10} {'最大回撤':<10}")
    print(f"{'-'*52}")
    for period in result.forward_periods:
        hr = result.hit_rates.get(period, "N/A")
        ex = result.avg_excess_returns.get(period, "N/A")
        cal = result.calmar_by_period.get(period, "N/A")
        dd = result.max_drawdown_by_period.get(period, "N/A")

        hr_str = f"{hr}%" if isinstance(hr, (int, float)) else str(hr)
        ex_str = f"{ex:+.1f}%" if isinstance(ex, (int, float)) else str(ex)
        cal_str = f"{cal:.2f}" if isinstance(cal, (int, float)) else str(cal)
        dd_str = f"{dd:.1f}%" if isinstance(dd, (int, float)) else str(dd)

        print(f"{period}个月     {hr_str:<10} {ex_str:<12} {cal_str:<10} {dd_str:<10}")

    # 最佳/最差单期
    print(f"\n--- 各周期最佳/最差单期 ---")
    for period in result.forward_periods:
        p = result.pool_returns[result.pool_returns["period_months"] == period]
        if p.empty:
            continue
        best = p.loc[p["avg_return"].idxmax()]
        worst = p.loc[p["avg_return"].idxmin()]
        print(f"  {period}个月: 最佳 {best['screening_date']} "
              f"({best['avg_return']:+.1f}%), "
              f"最差 {worst['screening_date']} ({worst['avg_return']:+.1f}%)")

    # Alpha 纯度分析
    alpha_info = _alpha_purity_analysis(result.pool_returns, result.benchmark_returns)
    annual = alpha_info.get("annual_breakdown", {})

    if annual:
        print(f"\n--- 分年度超额收益 (vs 沪深300) ---")
        for period, years in annual.items():
            print(f"\n  {period}个月前瞻:")
            for year in sorted(years.keys()):
                yr = years[year]
                print(f"    {year}: {yr['avg_return']:+.1f}% "
                      f"(n={yr['count']})")

    # L0 风格择时摘要
    if result.regime_log:
        rdf = pd.DataFrame(result.regime_log)
        print(f"\n--- L0 风格择时摘要 ---")
        for st in ["GROWTH_OK", "CAUTION", "DEFENSE"]:
            cnt = (rdf["regime_state"] == st).sum()
            if cnt > 0:
                print(f"  {st}: {cnt} 期")
        # 各通道触发率
        for ch in ["ch_A_growth_rel", "ch_B_rate", "ch_C_drawdown"]:
            label = ch.replace("ch_", "")
            rate = rdf[ch].mean() * 100 if ch in rdf.columns else 0
            print(f"  {label} 触发率: {rate:.0f}%")

    # 结论
    print(f"\n--- 综合结论 ---")
    best_period = max(result.calmar_by_period,
                      key=lambda k: result.calmar_by_period[k])
    print(f"  最佳前瞻周期: {best_period}个月 "
          f"(Calmar={result.calmar_by_period[best_period]:.2f})")

    ex_12m = result.avg_excess_returns.get(12)
    if ex_12m is not None:
        if ex_12m > 5:
            print(f"  ✅ 12个月超额收益 {ex_12m:+.1f}%，选股效果显著")
        elif ex_12m > 0:
            print(f"  ✅ 12个月超额收益 {ex_12m:+.1f}%，选股有效但需优化")
        else:
            print(f"  ⚠️ 12个月超额收益 {ex_12m:+.1f}%，需检查筛选逻辑")

    # 风格Beta提示
    print(f"\n  风格纯度提示:")
    print(f"  - 若超额仅在成长风格牛市中显著，则系统偏风格Beta")
    print(f"  - 2022年（成长股熊市）是核心压力测试点")

    print(f"{'='*70}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Growth OS 回测验证")
    parser.add_argument("--start", type=str, default="20220101",
                        help="回测起始日 YYYYMMDD (默认20220101)")
    parser.add_argument("--end", type=str, default="20260501",
                        help="回测结束日 YYYYMMDD (默认20260501)")
    parser.add_argument("--top", type=int, default=30,
                        help="每期选股数 (默认30)")
    parser.add_argument("--pool", type=int, default=800,
                        help="候选池大小 (默认800)")
    args = parser.parse_args()

    result = run_backtest(
        start_date=args.start,
        end_date=args.end,
        top_n=args.top,
        pool_size=args.pool,
    )

    print_backtest_report(result)

    # 归因分析
    attr = compute_attribution(result.pool_returns, result.benchmark_returns)
    print_attribution_report(attr)

    # 保存详细数据
    os.makedirs(DATA_PATHS["output_dir"], exist_ok=True)
    detail_path = os.path.join(
        DATA_PATHS["output_dir"],
        f"growth_backtest_{args.start}_{args.end}.csv",
    )
    merged = result.pool_returns.merge(
        result.benchmark_returns,
        on=["screening_date", "period_months"],
        how="left",
    )
    merged.to_csv(detail_path, index=False, encoding="utf-8-sig")
    logger.info(f"详细数据已保存: {detail_path}")

    # 保存 L0 状态日志
    if result.regime_log:
        regime_path = os.path.join(
            DATA_PATHS["output_dir"],
            f"regime_log_{args.start}_{args.end}.csv",
        )
        pd.DataFrame(result.regime_log).to_csv(
            regime_path, index=False, encoding="utf-8-sig")
        logger.info(f"L0状态日志已保存: {regime_path}")


if __name__ == "__main__":
    main()
