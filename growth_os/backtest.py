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
) -> BacktestResult:
    """运行 Growth OS 多点历史回测。

    Args:
        start_date: 回测起始日 YYYYMMDD
        end_date: 回测结束日 YYYYMMDD
        top_n: 每期选股数量
        forward_periods: 前瞻收益期数(月), 默认 [3, 6, 12]
        min_market_cap: 最低市值(亿元)
        pool_size: 每期候选池大小

    Returns:
        BacktestResult
    """
    if forward_periods is None:
        forward_periods = [3, 6, 12]

    screening_dates = _get_quarterly_dates(start_date, end_date)
    # 过滤掉太近的日期（前瞻期不足）
    max_forward = max(forward_periods)
    cutoff = pd.Timestamp(end_date) - pd.DateOffset(months=max_forward)
    screening_dates = [d for d in screening_dates
                       if pd.Timestamp(d) <= cutoff]

    logger.info(f"回测: {len(screening_dates)} 个季度筛选点, "
                f"Top{top_n}, 前瞻{forward_periods}个月")

    pool_returns_records = []
    benchmark_records = []

    for i, t_date in enumerate(screening_dates):
        logger.info(f"[{i+1}/{len(screening_dates)}] 筛选日期: {t_date}")

        try:
            # 加载数据 + 筛选
            df = load_growth_data(t_date)
            df = df[df["market_cap"] >= min_market_cap]
            if len(df) > pool_size:
                df = df.nlargest(pool_size, "market_cap")
            codes = df["code"].tolist()

            # 运行漏斗
            results = []
            for code in codes:
                try:
                    ind = get_industry(code)
                    lc, lc_reason = classify_lifecycle(code, t_date, ind)
                    funnel = run_funnel(code, t_date, ind, lc)
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
                    card = compute_composite(card, funnel)
                    results.append(card.to_dict())
                except Exception:
                    continue

            if not results:
                continue

            df_result = pd.DataFrame(results)
            df_result = df_result.sort_values(
                "composite_score", ascending=False
            ).head(top_n)

            top_codes = df_result["code"].tolist()

            # 计算前瞻收益
            for period in forward_periods:
                fwd_returns = []
                for code in top_codes:
                    ret = _get_forward_return(code, t_date, period, end_date)
                    if ret is not None:
                        fwd_returns.append(ret)

                if fwd_returns:
                    avg_ret = np.mean(fwd_returns)
                    median_ret = np.median(fwd_returns)
                    hit = sum(1 for r in fwd_returns if r > 0) / len(fwd_returns)
                else:
                    avg_ret = np.nan
                    median_ret = np.nan
                    hit = np.nan

                pool_returns_records.append({
                    "screening_date": t_date,
                    "period_months": period,
                    "n_stocks": len(fwd_returns),
                    "avg_return": round(avg_ret * 100, 2) if not np.isnan(avg_ret) else np.nan,
                    "median_return": round(median_ret * 100, 2) if not np.isnan(median_ret) else np.nan,
                    "hit_rate": round(hit * 100, 1) if not np.isnan(hit) else np.nan,
                })

                # 基准收益
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


if __name__ == "__main__":
    main()
