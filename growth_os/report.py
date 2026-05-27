"""个股深度体检报告 — Markdown 格式输出。"""
import os
import numpy as np
from datetime import datetime
from loguru import logger

from growth_os.config import LifecycleStage
from growth_os.data import get_financial_snapshot, get_price_data, get_industry
from growth_os.lifecycle import classify_lifecycle
from growth_os.funnel import run_funnel
from growth_os.scorecard import GrowthScorecard, compute_composite
from growth_os.sell_signals import check_sell_signals, get_sell_summary
from growth_os.industry_cal import get_industry_narrative
from growth_os.regime import compute_regime


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
        l1_verdict=funnel_result.get("l1_verdict", ""),
        l1_absolute_reds=funnel_result.get("l1_absolute_reds", []),
        l1_conditional_reds=funnel_result.get("l1_conditional_reds", []),
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
    l5_status = card.l5_status
    l5d = funnel_result["l5_details"]

    score_emoji = "🟢" if card.composite_score >= 70 else "🟡" if card.composite_score >= 50 else "🔴"
    qs = card.quality_score if not np.isnan(card.quality_score) else 0

    # 决策优先于分数区间：如有严重风险，色标降级
    has_critical_risk = (
        funnel_result.get("l3_details", {}).get("roic_vs_wacc", {}).get("score", 1) == 0
        or (l5_status == "ok" and not funnel_result["l5_details"].get("peg_ratio", {}).get("g_trusted", True))
    )
    if score_emoji == "🟡" and has_critical_risk:
        score_emoji = "🟠"  # 黄色降级为橙色：分数尚可但有严重风险

    lines.append(f"## 综合评分: {score_emoji} {card.composite_score:.1f}/100")
    lines.append(f"| 维度 | 分数 |")
    lines.append(f"|------|------|")
    lines.append(f"| 成长质量 (L1-L4) | **{qs:.1f}/100** |")
    if l5_status == "ok":
        ls = card.score_l5 if not np.isnan(card.score_l5) else 0
        lines.append(f"| 估值安全边际 (L5) | **{ls:.1f}/10** |")
    elif l5_status == "partial":
        ls = card.score_l5 if not np.isnan(card.score_l5) else 0
        lines.append(f"| 估值安全边际 (L5) | **{ls:.1f}/10** ⚠️ 数据不完整 |")
    else:
        lines.append(f"| 估值安全边际 (L5) | **N/A** 🔴 无法评估 |")
    lines.append(f"")
    lines.append(f"**决策**: {card.decision}")
    if not card.is_growth_eligible and card.block_reason:
        lines.append(f"**⛔ 成长资格**: ❌ 未通过 — {card.block_reason}")

    # L5 估值状态
    peg_val = l5d.get("peg_ratio", {}).get("value")
    pe_pct = l5d.get("pe_percentile", {}).get("value")
    g_proxy = l5d.get("peg_ratio", {}).get("g_proxy")
    g_source = l5d.get("peg_ratio", {}).get("g_source", "")
    g_source_map = {
        "ewa_yoy": "EWA历史YoY外推",
        "ewa_cl_crossvalidated": "EWA历史YoY外推+合同负债修正",
        "ewa_ocf_discounted": "EWA历史YoY外推(OCF含金量折扣)",
        "ewa_yoy_declining": "EWA历史YoY外推(近2季回落修正)",
        "fallback_cagr3y": "3年CAGR回退估算",
        "ewa_floor": "极低增速保底",
    }
    g_source_label = g_source_map.get(g_source, g_source)

    if l5_status == "ok":
        g_note = f" (g*={g_proxy:.0f}%, {g_source_label})" if g_proxy is not None else ""
        lines.append(f"**估值状态**: ✅ 可评估 — PEG={peg_val:.1f}{g_note}, PE分位={pe_pct:.0f}%")
        lines.append(f"**g* 说明**: g* 由{g_source_label}，非分析师一致预期CAGR")
    elif l5_status == "partial":
        lines.append(f"**估值状态**: ⚠️ 数据不完整 — 仅增长加速度可用，估值上限 5/10")
    else:
        lines.append(f"**估值状态**: 🔴 无法评估 — L5未参与综合分，请人工核实")

    lines.append(f"**生命周期判定**: {lc_reason}")
    lines.append(f"")

    # 决策卡片
    lines.append(f"## 决策卡片")
    lines.append(f"")

    # 正面因素
    positives = []
    if qs >= 75: positives.append(f"成长质量优秀（{qs:.0f}/100）")
    elif qs >= 60: positives.append(f"成长质量良好（{qs:.0f}/100）")

    # 非成长持仓：估值低反映周期下行预期，非安全边际
    if not card.is_growth_eligible:
        if l5_status == "ok" and hasattr(card, 'pe_percentile') and card.pe_percentile is not None and card.pe_percentile < 30:
            positives.append(f"PE处于历史低位（分位{card.pe_percentile:.0f}%，市场已反映悲观预期）")
    else:
        if l5_status == "ok" and card.score_l5 >= 7: positives.append(f"估值安全边际充足（{card.score_l5:.0f}/10）")
        elif l5_status == "ok" and card.score_l5 >= 4: positives.append(f"估值安全边际尚可（{card.score_l5:.0f}/10）")

    if card.roic and card.roic_minus_wacc and card.roic_minus_wacc > 3: positives.append(f"ROIC显著优于WACC（利差{card.roic_minus_wacc:.1f}pp）")
    if hasattr(card, 'pe_percentile') and card.pe_percentile and card.pe_percentile < 40 and card.is_growth_eligible: positives.append(f"PE行业分位偏低（{card.pe_percentile:.0f}%）")

    # 风险因素
    risks = []
    pe_hist = funnel_result["l5_details"].get("pe_hist_pct", {})
    if pe_hist.get("value", 0) > 90: risks.append(f"PE处于自身历史极高位（分位{pe_hist['value']:.0f}%），估值均值回归风险高")
    elif pe_hist.get("value", 0) > 70: risks.append(f"PE处于自身历史高位（分位{pe_hist['value']:.0f}%），绝对估值不低，关注均值回归风险")
    if l5_status == "partial": risks.append("估值数据不完整，安全边际判断受限")
    if l5_status == "missing": risks.append("估值完全不可用，需人工核实PE后评估")
    if card.peg and card.peg > 2.5: risks.append(f"PEG偏高（{card.peg:.1f}），增速可能已被充分定价")

    # L5 PEG g* 可信度
    g_trusted = funnel_result["l5_details"].get("peg_ratio", {}).get("g_trusted", True)
    if l5_status == "ok" and not g_trusted:
        peg_details = funnel_result["l5_details"]["peg_ratio"]
        g_pct = peg_details.get("g_proxy", "?")
        risks.append(f"⚠️ PEG可信度低：g*={g_pct}%与近期营收增速背离，PEG可能失真")

    # L3 ROIC毁灭价值
    l3d = funnel_result.get("l3_details", {})
    roic_wacc = l3d.get("roic_vs_wacc", {})
    if roic_wacc.get("score", 1) == 0:
        risks.append(f"🔴 ROIC<WACC（毁灭价值）")

    # L1 排雷信号
    if funnel_result.get("l1_red_flags"):
        risks.append(f"🟡 排雷警告：{', '.join(funnel_result['l1_red_flags'][:2])}")

    # 卖出信号（ROIC跌破WACC / 应收飙升等）
    if sell_signals:
        for s in sell_signals[:2]:
            if s.get("triggered") and s.get("severity") in ("red", "yellow"):
                risks.append(f"{'🔴' if s['severity'] == 'red' else '🟡'} {s['signal']}")

    # 探针信号
    probe_green = 0
    probe_yellow = 0
    probe_red = 0
    probe_unknown = 0
    try:
        from growth_os.growth_probes import run_all_probes
        probes = run_all_probes(code, t_date)
        for p in probes:
            if p["level"] == "green": probe_green += 1
            elif p["level"] == "yellow": probe_yellow += 1
            elif p["level"] == "red": probe_red += 1
            elif p["level"] == "unknown": probe_unknown += 1
    except ImportError:
        probes = []

    lines.append(f"| | 评估 |")
    lines.append(f"|------|------|")
    lines.append(f"| **优势** | {', '.join(positives) if positives else '无明显突出优势'} |")
    lines.append(f"| **风险** | {', '.join(risks) if risks else '未发现明显风险因素'} |")
    # 探针摘要
    if probe_unknown > 0:
        probe_summary = f"✅ {probe_green}🟢 / {probe_yellow}🟡 / {probe_red}🔴 / {probe_unknown}⚠️未知"
    else:
        probe_summary = f"✅ {probe_green}🟢 / {probe_yellow}🟡 / {probe_red}🔴"
    lines.append(f"| **增长持续性** | {probe_summary} |")

    # Regime 状态 + 连续仓位
    try:
        regime = compute_regime(t_date)
        from growth_os.regime_continuous import ContinuousRegime
        cr = ContinuousRegime()
        position = cr.compute(t_date)
        if regime.is_defense:
            regime_tag = f"（⚠️ 当前 DEFENSE 期，即使高分也不建议建仓；模型仓位 {position:.0f}%）"
        elif regime.is_ok:
            regime_tag = f"（GROWTH_OK 期，建议成长仓位 {position:.0f}%）"
        else:
            regime_tag = f"（CAUTION 期，建议成长仓位 {position:.0f}%）"
    except Exception:
        regime_tag = ""

    # 综合建议
    if qs >= 75 and l5_status == "ok" and probe_red == 0:
        suggestion = f"🟢 高质量成长股，估值合理，增长信号健康——可纳入核心持仓考量{regime_tag}"
    elif qs >= 75 and probe_red > 0:
        suggestion = f"🟡 优质但有隐忧——建议关注探针风险信号，控制单票仓位{regime_tag}"
    elif qs >= 75 and l5_status != "ok":
        suggestion = "🟡 基本面优异但估值状态不明——建议人工确认PE后决策"
    elif qs >= 60:
        suggestion = "🟡 中等质量——可作为观察池标的，等待更好买点或基本面改善"
    else:
        suggestion = "🔴 质量偏低——不建议重点关注"

    lines.append(f"| **综合建议** | {suggestion} |")
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

    # 轨迹层 — 关键指标演化方向
    traj = _build_trajectory(code, t_date)
    if traj:
        lines.append(f"## 轨迹层（演化方向）")
        lines.append(f"")
        for item in traj:
            lines.append(f"- {item}")
        lines.append(f"")

    # L1 排雷
    verdict_label = {"pass": "✅ 通过", "review": "🟡 条件红灯(观察)", "kill_absolute": "❌ 绝对红灯淘汰", "kill_conditional": "❌ 条件红灯累积淘汰"}
    verdict_display = verdict_label.get(funnel_result.get("l1_verdict"), funnel_result.get("l1_verdict", "?"))
    lines.append(f"## L1 排雷 — {verdict_display}")
    abs_reds = funnel_result.get("l1_absolute_reds", [])
    cond_reds = funnel_result.get("l1_conditional_reds", [])
    if abs_reds:
        lines.append(f"**🔴 绝对红灯**: {', '.join(abs_reds)}")
    if cond_reds:
        lines.append(f"**🟡 条件红灯**: {', '.join(cond_reds)}")
    if card.l1_red_flags:
        lines.append(f"**全部红灯**: {', '.join(card.l1_red_flags)}")
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
    l4d = funnel_result["l4_details"]
    peer_rank = l4d.get("peer_rank", {})
    rank_label = peer_rank.get("label", "") if peer_rank else ""
    lines.append(f"## L4 行业校准 — {card.score_l4:.1f}/10 — {rank_label}")
    for key, val in l4d.items():
        if key == "total" or key == "peer_rank":
            continue
        lines.append(f"- **{key}**: {val.get('label', 'N/A')}")
    lines.append(f"")

    # L5 预期差
    l5_score_display = card.score_l5 if not np.isnan(card.score_l5) else 0
    if l5_status == "ok":
        g_trusted = l5d.get("peg_ratio", {}).get("g_trusted", True)
        l5_suffix = " ⚠️ 低可信（PEG失真压分）" if not g_trusted else " ✅"
        lines.append(f"## L5 预期差 — {l5_score_display:.1f}/10{l5_suffix}")
    elif l5_status == "partial":
        lines.append(f"## L5 预期差 — {l5_score_display:.1f}/10 ⚠️ (PE/PEG缺失)")
    else:
        lines.append(f"## L5 预期差 — N/A 🔴 (估值不可用)")

    for key, val in l5d.items():
        if key == "total":
            continue
        lines.append(f"- **{key}**: {val.get('label', 'N/A')} (得分: {val.get('score', 0):.1f})")

    # PEG 适用域声明 — 按行业自动标注
    if l5_status == "ok":
        from growth_os.config import PEG_CONFIDENCE, PEG_CONFIDENCE_DEFAULT
        peg_conf = PEG_CONFIDENCE.get(industry_l3, PEG_CONFIDENCE_DEFAULT)
        level = peg_conf["level"]
        note = peg_conf["note"]
        driver = peg_conf["driver"]
        if level == "misleading":
            lines.append(f"> 🔴 **PEG 适用域 — {driver}**：{note}")
        elif level == "caution":
            lines.append(f"> ⚠️ **PEG 适用域 — {driver}**：{note}")
        else:
            lines.append(f"> ✅ **PEG 适用域 — {driver}**：{note}")

    lines.append(f"")

    # 增长来源探针
    try:
        from growth_os.growth_probes import run_all_probes
        probes = run_all_probes(code, t_date)
        lines.append(f"## 增长来源探针（持续性判断）")
        lines.append(f"")
        for p in probes:
            lines.append(f"- {p['label']}")
        lines.append(f"")
        lines.append(f"> 探针不参与综合评分，仅作为增长持续性参考。")
        lines.append(f"> 🟢=正面信号 🟡=中性/关注 🔴=风险信号")
        lines.append(f"")
    except ImportError:
        pass

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


def _build_trajectory(code: str, t_date: str) -> list[str]:
    """构建关键指标轨迹层 — 展示演化方向而非截面状态。

    追踪毛利率/ROIC/营收增速/净利率的连续变化方向。
    """
    from growth_os.data import get_quarterly_series
    import numpy as np

    items = []
    # 单位：绝对值用%，变化量用pp
    metrics = [
        ("gross_margin", "毛利率"),
        ("roic", "ROIC"),
        ("revenue_yoy", "营收增速"),
        ("net_margin", "净利率"),
    ]

    for field, name in metrics:
        series = get_quarterly_series(code, field, n_quarters=8, t_date=t_date).dropna()
        if len(series) < 4:
            items.append(f"⚪ {name}：数据不足")
            continue

        recent = series.iloc[-4:].mean()
        older = series.iloc[-8:-4].mean() if len(series) >= 8 else series.iloc[:4].mean()

        if older <= 0:
            items.append(f"⚪ {name}：无法比较（基期≤0）")
            continue

        delta = recent - older

        # 判断连续季度方向
        vals = series.values
        ups = sum(1 for i in range(1, min(4, len(vals))) if vals[-i] > vals[-(i+1)])
        downs = sum(1 for i in range(1, min(4, len(vals))) if vals[-i] < vals[-(i+1)])

        if abs(delta) < 1:
            items.append(f"➡️ {name}：近4季稳定（{recent:.1f}%，Δ{delta:+.1f}pp）")
        elif delta > 0:
            trend_word = "连续提升" if ups >= 2 else "边际改善"
            items.append(f"📈 {name}：近4季{trend_word}（{recent:.1f}%，Δ{delta:+.1f}pp）")
        else:
            trend_word = "连续下滑" if downs >= 2 else "边际走弱"
            items.append(f"📉 {name}：近4季{trend_word}（{recent:.1f}%，Δ{delta:+.1f}pp）")

        # 最新季度与4Q均值显著偏离时额外标注
        latest = vals[-1] if len(vals) > 0 else None
        if latest is not None and abs(latest - recent) > abs(recent) * 0.5 and abs(recent) > 2:
            items.append(f"  ⚠️ 最新季度{latest:.1f}%与近4季均值({recent:.1f}%)显著偏离")

    return items
