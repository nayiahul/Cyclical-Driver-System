#!/usr/bin/env python3
"""批量筛选入口 — 全市场扫描输出成长股观察池。

用法:
    .venv/bin/python -m growth_os.run_screen --date 20260519 --top 100
    .venv/bin/python -m growth_os.run_screen --date 20260519 --code 600519
"""
import os
import sys
import argparse
import pandas as pd
import numpy as np
from datetime import datetime
from loguru import logger

from growth_os.config import DATA_PATHS, EXCLUDED_INDUSTRIES_L1
from growth_os.data import load_growth_data, get_industry
from growth_os.lifecycle import classify_lifecycle
from growth_os.funnel import run_funnel
from growth_os.scorecard import GrowthScorecard, compute_composite
from growth_os.report import generate_report


def screen_all(t_date: str, top_n: int = 100, min_market_cap: float = 20.0) -> pd.DataFrame:
    """全市场成长股筛选。

    Args:
        t_date: 数据日期 YYYYMMDD
        top_n: 输出前 N 只
        min_market_cap: 最低市值(亿元)

    Returns:
        DataFrame 打分卡结果
    """
    logger.info(f"=== 全市场成长股筛选: {t_date} ===")

    # 加载全市场快照
    df = load_growth_data(t_date)
    logger.info(f"全市场: {len(df)} 只")

    # 基础过滤
    df = df[df["market_cap"] >= min_market_cap].copy()
    logger.info(f"市值过滤(>={min_market_cap}亿): {len(df)} 只")

    # 排除金融地产
    df = df[~df["industry_l1"].isin(EXCLUDED_INDUSTRIES_L1)].copy()
    logger.info(f"排除金融地产后: {len(df)} 只")

    # 必须有营收
    df = df[df["revenue"] > 0].copy()
    logger.info(f"有营收: {len(df)} 只")

    # 限制筛选数量（全市场太慢，取市值前1500只做大池）
    df = df.sort_values("market_cap", ascending=False).head(1500).copy()
    codes = df["code"].tolist()
    logger.info(f"筛选池: {len(codes)} 只 (市值前1500)")

    results = []
    for i, code in enumerate(codes):
        if (i + 1) % 100 == 0:
            logger.info(f"进度: {i+1}/{len(codes)}")
        try:
            industry_l3 = get_industry(code)
            lifecycle, lc_reason = classify_lifecycle(code, t_date, industry_l3)
            funnel = run_funnel(code, t_date, industry_l3, lifecycle)

            card = GrowthScorecard(
                code=code,
                name=df[df["code"] == code].iloc[0].get("name", code) if "name" in df.columns else code,
                industry_l3=industry_l3,
                industry_l1=df[df["code"] == code].iloc[0].get("industry_l1", ""),
                lifecycle=lifecycle,
                lifecycle_reason=lc_reason,
                pass_l1=funnel["pass_l1"],
                l1_red_flags=funnel["l1_red_flags"],
                score_l2=funnel.get("score_l2", np.nan),
                score_l3=funnel.get("score_l3", np.nan),
                score_l4=funnel.get("score_l4", np.nan),
                score_l5=funnel.get("score_l5", np.nan),
            )
            card = compute_composite(card, funnel)
            results.append(card.to_dict())
        except Exception as e:
            logger.debug(f"{code} 处理异常: {e}")
            continue

    result_df = pd.DataFrame(results)
    if len(result_df) == 0:
        logger.error("无有效结果")
        return pd.DataFrame()

    # 排序
    result_df = result_df.sort_values("composite_score", ascending=False)
    result_df = result_df.head(top_n)

    # 输出
    os.makedirs(DATA_PATHS["output_dir"], exist_ok=True)
    out_path = os.path.join(DATA_PATHS["output_dir"],
                            f"growth_pool_{t_date}.csv")
    result_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    logger.info(f"观察池已保存: {out_path}")

    # 打印摘要
    _print_summary(result_df)

    return result_df


def _print_summary(df: pd.DataFrame, n: int = 30):
    """打印筛选摘要。"""
    print(f"\n{'='*80}")
    print(f"  成长股观察池 Top {min(n, len(df))}")
    print(f"{'='*80}")
    print(f"{'代码':<8} {'名称':<10} {'行业':<14} {'阶段':<6} {'综合':>5} {'L2':>5} {'L3':>5} {'L4':>5} {'L5':>5} {'决策'}")
    print(f"{'-'*90}")
    for _, r in df.head(n).iterrows():
        print(f"{r['code']:<8} {str(r['name'])[:10]:<10} "
              f"{str(r['industry_l3'])[:14]:<14} {str(r['lifecycle'])[:6]:<6} "
              f"{r['composite_score']:>5.1f} {r['score_l2']:>5.1f} "
              f"{r['score_l3']:>5.1f} {r['score_l4']:>5.1f} {r['score_l5']:>5.1f} "
              f"{str(r['decision'])[:8]}")

    print(f"\n生命周期分布:")
    for stage in df["lifecycle"].value_counts().index:
        print(f"  {stage}: {df['lifecycle'].value_counts()[stage]} 只")

    print(f"\n决策分布:")
    for dec in df["decision"].value_counts().index:
        print(f"  {dec}: {df['decision'].value_counts()[dec]} 只")


def main():
    parser = argparse.ArgumentParser(description="成长股挖掘系统 — 批量筛选/个股体检")
    parser.add_argument("--date", type=str, default=None,
                        help="数据日期 YYYYMMDD (默认最新)")
    parser.add_argument("--top", type=int, default=100,
                        help="输出前N只 (默认100)")
    parser.add_argument("--code", type=str, default=None,
                        help="单只股票代码 (个股深度体检模式)")
    parser.add_argument("--min-cap", type=float, default=20.0,
                        help="最低市值(亿元) (默认20)")
    args = parser.parse_args()

    t_date = args.date or datetime.now().strftime("%Y%m%d")

    if args.code:
        # 个股深度体检
        report_path = generate_report(args.code, t_date)
        if report_path:
            with open(report_path, "r") as f:
                print(f.read())
    else:
        # 全市场筛选
        screen_all(t_date, top_n=args.top, min_market_cap=args.min_cap)


if __name__ == "__main__":
    main()
