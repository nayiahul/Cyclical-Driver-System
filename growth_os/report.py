"""个股深度体检报告 — Markdown 格式输出。"""
import os
from datetime import datetime
from loguru import logger

from growth_os.config import LifecycleStage
from growth_os.data import get_financial_snapshot, get_price_data, get_industry
from growth_os.lifecycle import classify_lifecycle
from growth_os.funnel import run_funnel
from growth_os.scorecard import GrowthScorecard, compute_composite
from growth_os.sell_signals import check_sell_signals, get_sell_summary
from growth_os.industry_cal import get_industry_narrative


def generate_report(code: str, t_date: str, output_dir: str = "output") -> str:
    """生成个股深度体检报告 (Markdown)。

    Returns:
        报告文件路径
    """
    # ---- 收集数据 ----
    snap = get_financial_snapshot(t_date)
    row = snap[snap["code"] == code]
    if row.empty:
        logger.error(f"股票 {code} 无财务数据")
        return ""
    row = row.iloc[0]

    name = _get_stock_name(code)
    industry_l3 = get_industry(code)

    lifecycle, lc_reason = classify_lifecycle(code, t_date, industry_l3)
    funnel_result = run_funnel(code, t_date, industry_l3, lifecycle)

    card = GrowthScorecard(
        code=code,
        name=name,
        industry_l3=industry_l3,
        lifecycle=lifecycle,
        lifecycle_reason=lc_reason,
        pass_l1=funnel_result["pass_l1"],
        l1_red_flags=funnel_result["l1_red_flags"],
        score_l2=funnel_result["score_l2"],
        score_l3=funnel_result["score_l3"],
        score_l4=funnel_result["score_l4"],
        score_l5=funnel_result["score_l5"],
    )
    card = compute_composite(card, funnel_result)

    sell_signals = check_sell_signals(code, t_date)
    sell_summary = get_sell_summary(sell_signals)

    narrative = get_industry_narrative(industry_l3)

    # ---- 生成 Markdown ----
    lines = []
    lines.append(f"# 成长股深度体检报告: {name} ({code})")
    lines.append(f"")
    lines.append(f"**日期**: {t_date}")
    lines.append(f"**行业**: {industry_l3}")
    lines.append(f"**生命周期**: {lifecycle.value}")
    lines.append(f"**行业叙事**: {narrative}")
    lines.append(f"")

    # 摘要
    score_emoji = "🟢" if card.composite_score >= 70 else "🟡" if card.composite_score >= 50 else "🔴"
    lines.append(f"## 综合评分: {score_emoji} {card.composite_score:.1f}/100")
    lines.append(f"**决策**: {card.decision}")
    lines.append(f"**生命周期判定**: {lc_reason}")
    lines.append(f"")

    # 飞轮四象限
    lines.append(f"## 飞轮四象限")
    lines.append(f"")
    lines.append(f"| 指标 | 值 | 趋势 |")
    lines.append(f"|------|-----|------|")
    rev_yoy = row.get("revenue_yoy") or 0
    gm = row.get("gross_margin") or 0
    roic_v = card.roic or 0
    ocf_ratio = card.ocf_profit_ratio_3y or 0

    lines.append(f"| 营收增速 | {rev_yoy:.1f}% | {card.growth_accel or 'N/A'} |")
    lines.append(f"| 毛利率 | {gm:.1f}% | {card.gross_margin_trend} |")
    lines.append(f"| ROIC | {roic_v:.1f}% | {'>WACC' if card.roic_minus_wacc and card.roic_minus_wacc > 0 else '<WACC'} |")
    lines.append(f"| OCF/净利润 | {ocf_ratio:.2f} | {'健康' if ocf_ratio > 0.8 else '关注'} |")
    lines.append(f"")

    # L1 排雷
    lines.append(f"## L1 排雷 — {'✅ 通过' if card.pass_l1 else '❌ 淘汰'}")
    if card.l1_red_flags:
        lines.append(f"**红灯**: {', '.join(card.l1_red_flags)}")
    lines.append(f"")
    l1d = funnel_result["l1_details"]
    for key, val in l1d.items():
        if key.startswith("_"):
            continue
        flag = "🔴" if val.get("red") else "✅"
        lines.append(f"- {flag} **{key}**: {val.get('detail', 'N/A')}")
    lines.append(f"")

    # L2 护城河
    lines.append(f"## L2 护城河 — {card.score_l2:.1f}/10")
    l2d = funnel_result["l2_details"]
    for key, val in l2d.items():
        if key == "total":
            continue
        lines.append(f"- **{key}**: {val.get('label', 'N/A')} (得分: {val.get('score', 0):.1f})")
    lines.append(f"")

    # L3 资本效率
    lines.append(f"## L3 资本效率 — {card.score_l3:.1f}/10")
    l3d = funnel_result["l3_details"]
    for key, val in l3d.items():
        if key == "total":
            continue
        lines.append(f"- **{key}**: {val.get('label', 'N/A')} (得分: {val.get('score', 0):.1f})")
    lines.append(f"")

    # L4 行业校准
    lines.append(f"## L4 行业校准 — {card.score_l4:.1f}/10")
    l4d = funnel_result["l4_details"]
    for key, val in l4d.items():
        if key == "total":
            continue
        lines.append(f"- **{key}**: {val.get('label', 'N/A')}")
    lines.append(f"")

    # L5 预期差
    lines.append(f"## L5 预期差 — {card.score_l5:.1f}/10")
    l5d = funnel_result["l5_details"]
    for key, val in l5d.items():
        if key == "total":
            continue
        lines.append(f"- **{key}**: {val.get('label', 'N/A')} (得分: {val.get('score', 0):.1f})")
    lines.append(f"")

    # 卖出信号
    lines.append(f"## 卖出信号")
    lines.append(f"{sell_summary}")
    for s in sell_signals:
        if s["triggered"]:
            lines.append(f"- {s['severity'].upper()}: **{s['signal']}** — {s['reason']}")
    lines.append(f"")

    # 脚注
    lines.append(f"---")
    lines.append(f"*报告由 Growth OS 自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    report_md = "\n".join(lines)

    # 写入文件
    os.makedirs(output_dir, exist_ok=True)
    fpath = os.path.join(output_dir, f"growth_report_{code}_{t_date}.md")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(report_md)

    logger.info(f"报告已保存: {fpath}")
    return fpath


def _get_stock_name(code: str) -> str:
    """获取股票名称（从行业映射文件）。"""
    import pandas as pd
    from growth_os.config import DATA_PATHS
    path = DATA_PATHS["sw_industry_map"]
    try:
        df = pd.read_csv(path, dtype={"证券代码": str})
        row = df[df["证券代码"] == code]
        if not row.empty:
            return row.iloc[0]["证券名称"]
    except Exception:
        pass
    return code
