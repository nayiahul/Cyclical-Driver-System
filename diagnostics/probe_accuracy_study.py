#!/usr/bin/env python3
"""探针历史准确率回测 — 量化探针信号组合的预测能力。

跨 2019-2024 各季度快照，对每只样本股：
  1. 运行 4 项增长来源探针
  2. 记录探针信号模式（绿/黄/红计数）
  3. 追踪 12 个月前瞻收益
  4. 按信号模式分组统计平均超额收益和命中率

用法:
    source .venv/bin/activate
    python diagnostics/probe_accuracy_study.py
"""
import os
import sys
import time
import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from growth_os.data import get_financial_snapshot, get_price_data, load_industry_map
from growth_os.growth_probes import (
    probe_order_leadership, probe_capex_efficiency, probe_margin_resilience,
    _level_to_score,
)


# ═══════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════

QUARTER_DATES = [
    "20210630", "20210930", "20211231",
    "20220331", "20220630", "20220930", "20221231",
    "20230331", "20230630", "20230930", "20231231",
    "20240331", "20240630",
]

FORWARD_MONTHS = 12         # 前瞻收益周期
SAMPLE_PER_PERIOD = 80      # 每期抽样数
MIN_MARKET_CAP = 50         # 最低市值(亿元)
SKIP_CUSTOMER_PROBE = True  # 跳过探针4(客户集中度，需PDF下载)，仅用探针1-3
SEED = 42

OUTPUT_PATH = "diagnostics/probe_accuracy_results.csv"


# ═══════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════

def get_forward_return(code: str, start_date: str, months: int) -> float | None:
    """计算前瞻收益。"""
    pdf = get_price_data(code)
    if pdf is None or pdf.empty:
        return None

    t0 = pd.Timestamp(start_date)
    t1 = t0 + pd.DateOffset(months=months)
    tmax = pdf["date"].max()

    # 找最接近 start_date 的交易日
    pdf_before = pdf[pdf["date"] <= t0]
    if pdf_before.empty:
        return None
    p0 = pdf_before.iloc[-1]["close"]

    # 找最接近 t1 的交易日（不超过数据截止日）
    pdf_after = pdf[(pdf["date"] > t0) & (pdf["date"] <= min(t1, tmax))]
    if pdf_after.empty:
        return None
    p1 = pdf_after.iloc[-1]["close"]

    if p0 <= 0:
        return None
    return float(p1 / p0 - 1)


def classify_pattern(probes: list[dict]) -> dict:
    """将探针结果分类为信号模式。"""
    counts = {"green": 0, "yellow": 0, "red": 0, "unknown": 0}
    for p in probes:
        counts[p["level"]] = counts.get(p["level"], 0) + 1

    return {
        "n_green": counts["green"],
        "n_yellow": counts["yellow"],
        "n_red": counts["red"],
        "n_unknown": counts["unknown"],
        "pattern": f"{counts['green']}G{counts['yellow']}Y{counts['red']}R",
        "total_score": sum(p.get("score", 0) or 0 for p in probes),
    }


# ═══════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════

def run_study():
    random.seed(SEED)
    all_rows = []
    dates_to_run = [d for d in QUARTER_DATES if d < "20250331"]  # 留12M前瞻空间

    logger.info(f"探针准确率回测: {len(dates_to_run)} 期 × ~{SAMPLE_PER_PERIOD} 只/期")
    t_start = time.time()

    for i, t_date in enumerate(dates_to_run):
        t_loop = time.time()

        # 获取当期快照
        try:
            snap = get_financial_snapshot(t_date)
        except Exception as e:
            logger.warning(f"{t_date}: 快照失败 {e}")
            continue

        # 筛选候选池
        snap = snap[snap["market_cap"] >= MIN_MARKET_CAP].copy() if "market_cap" in snap.columns else snap
        snap = snap[snap["revenue"] > 0].copy() if "revenue" in snap.columns else snap

        if len(snap) < SAMPLE_PER_PERIOD:
            sample = snap
        else:
            sample = snap.sample(n=SAMPLE_PER_PERIOD, random_state=SEED + i)

        codes = sample["code"].tolist()
        n_done = 0

        for code in codes:
            try:
                if SKIP_CUSTOMER_PROBE:
                    probes = [
                        {"name": "订单领先性", **probe_order_leadership(code, t_date)},
                        {"name": "CAPEX效率", **probe_capex_efficiency(code, t_date)},
                        {"name": "毛利率韧性", **probe_margin_resilience(code, t_date)},
                    ]
                    for p in probes:
                        p["score"] = _level_to_score(p["level"])
                else:
                    from growth_os.growth_probes import run_all_probes
                    probes = run_all_probes(code, t_date)
                pattern = classify_pattern(probes)

                fwd_ret = get_forward_return(code, t_date, FORWARD_MONTHS)
                if fwd_ret is None:
                    continue

                all_rows.append({
                    "screening_date": t_date,
                    "code": code,
                    **pattern,
                    "fwd_12m_return": round(fwd_ret * 100, 2),
                })
                n_done += 1
            except Exception:
                continue

        elapsed = time.time() - t_loop
        total_elapsed = time.time() - t_start
        eta = total_elapsed / (i + 1) * (len(dates_to_run) - i - 1) / 60 if i > 0 else 0
        logger.info(f"{t_date}: {n_done}/{len(codes)} 只有效 "
                    f"({elapsed:.0f}s | ETA {eta:.0f}min)")

    # ═══════════════════════════════════════════
    # 汇总统计
    # ═══════════════════════════════════════════
    df = pd.DataFrame(all_rows)
    if df.empty:
        logger.error("无有效数据点")
        return

    df.to_csv(OUTPUT_PATH, index=False)
    logger.info(f"原始数据: {len(df)} 行 → {OUTPUT_PATH}")

    # 按信号模式分组统计
    print("\n" + "=" * 80)
    print("  探针信号模式 vs 12M 前瞻收益")
    print("=" * 80)
    print(f"{'模式':<12} {'样本数':>6} {'平均收益':>8} {'中位收益':>8} {'正收益率':>8} {'超额(>0%)':>8}")
    print("-" * 60)

    # 按 total_score 分档
    df["score_bin"] = pd.cut(
        df["total_score"], bins=[-0.1, 0.5, 1.5, 2.5, 4.0],
        labels=["0-0.5(差)", "0.5-1.5(一般)", "1.5-2.5(良好)", "2.5-4(优秀)"]
    )

    for bin_name in ["0-0.5(差)", "0.5-1.5(一般)", "1.5-2.5(良好)", "2.5-4(优秀)"]:
        sub = df[df["score_bin"] == bin_name]
        if len(sub) < 5:
            continue
        avg_ret = sub["fwd_12m_return"].mean()
        med_ret = sub["fwd_12m_return"].median()
        win_rate = (sub["fwd_12m_return"] > 0).mean() * 100
        print(f"{bin_name:<12} {len(sub):>6} {avg_ret:>+7.1f}% {med_ret:>+7.1f}% {win_rate:>7.0f}%")

    # 按红/绿灯模式
    print(f"\n{'模式':<12} {'样本数':>6} {'平均收益':>8} {'中位收益':>8} {'正收益率':>8}")
    print("-" * 55)
    df["simple_pattern"] = df.apply(
        lambda r: f"{int(r['n_green'])}G{int(r['n_red'])}R", axis=1
    )
    for pat in sorted(df["simple_pattern"].unique()):
        sub = df[df["simple_pattern"] == pat]
        if len(sub) < 5:
            continue
        avg_ret = sub["fwd_12m_return"].mean()
        med_ret = sub["fwd_12m_return"].median()
        win_rate = (sub["fwd_12m_return"] > 0).mean() * 100
        print(f"{pat:<12} {len(sub):>6} {avg_ret:>+7.1f}% {med_ret:>+7.1f}% {win_rate:>7.0f}%")

    print(f"\n总样本: {len(df)} | 总耗时: {(time.time() - t_start)/60:.0f}min")

    # 输出建议文案
    print("\n--- 报告可引用 ---")
    for pat in sorted(df["simple_pattern"].unique(), key=lambda x: df[df["simple_pattern"]==x]["fwd_12m_return"].mean(), reverse=True):
        sub = df[df["simple_pattern"] == pat]
        if len(sub) < 10:
            continue
        avg_ret = sub["fwd_12m_return"].mean()
        win_rate = (sub["fwd_12m_return"] > 0).mean() * 100
        print(f"  {pat}: {len(sub)}样本, 12M平均超额{avg_ret:+.1f}%, 正收益率{win_rate:.0f}%")


if __name__ == "__main__":
    run_study()
