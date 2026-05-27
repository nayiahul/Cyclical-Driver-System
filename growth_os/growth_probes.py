"""增长来源探针 — 判断增长可持续性的四个观测维度。

不参与综合评分，仅输出标签+一句话。全部使用已有财务数据。
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from loguru import logger

from growth_os.data import get_financial_snapshot, get_quarterly_series


# ═══════════════════════════════════════════════
# 探针 1：订单领先性
# ═══════════════════════════════════════════════

def probe_order_leadership(code: str, t_date: str) -> dict:
    """合同负债是否领先营收——增长来自需求漏斗还是价格效应。

    Returns:
        {"label": str, "level": "green"|"yellow"|"red"|"unknown"}
    """
    cl_series = get_quarterly_series(code, "contract_liabilities", n_quarters=8, t_date=t_date).dropna()
    rev_yoy_series = get_quarterly_series(code, "revenue_yoy", n_quarters=4, t_date=t_date).dropna()

    if len(cl_series) < 4:
        return {"label": "⚠️ 合同负债数据不足", "level": "unknown"}

    cl_recent = cl_series.iloc[-4:].mean()
    cl_old = cl_series.iloc[-8:-4].mean() if len(cl_series) >= 8 else cl_series.iloc[:4].mean()
    cl_growth = (cl_recent / cl_old - 1) * 100 if cl_old > 0 else None

    rev_yoy = rev_yoy_series.iloc[-1] if len(rev_yoy_series) > 0 else None

    if cl_growth is None or rev_yoy is None:
        return {"label": "⚠️ 数据不足", "level": "unknown"}

    # 合同负债增速显著高于营收增速 → 需求漏斗充盈
    if cl_growth > 0 and rev_yoy > 0 and cl_growth > rev_yoy * 0.8:
        return {"label": f"🟢 需求漏斗充盈（合同负债+{cl_growth:.0f}%，营收+{rev_yoy:.0f}%）", "level": "green"}
    elif cl_growth > 0:
        return {"label": f"🟡 订单同步增长（合同负债+{cl_growth:.0f}%）", "level": "yellow"}
    elif cl_growth > -10:
        return {"label": f"🟡 订单持平", "level": "yellow"}
    else:
        return {"label": f"🔴 订单萎缩（合同负债{cl_growth:.0f}%），警惕增长后劲", "level": "red"}


# ═══════════════════════════════════════════════
# 探针 2：CAPEX 效率
# ═══════════════════════════════════════════════

def probe_capex_efficiency(code: str, t_date: str) -> dict:
    """CAPEX 扩张是否伴随 ROIC 提升——健康扩产 vs 周期顶部冲动。

    Returns:
        {"label": str, "level": "green"|"yellow"|"red"|"unknown"}
    """
    capex_series = get_quarterly_series(code, "capex_cash", n_quarters=8, t_date=t_date).dropna()
    roic_series = get_quarterly_series(code, "roic", n_quarters=8, t_date=t_date).dropna()

    if len(capex_series) < 4 or len(roic_series) < 4:
        return {"label": "⚠️ CAPEX/ROIC 数据不足", "level": "unknown"}

    capex_recent = capex_series.iloc[-4:].sum()
    capex_old = capex_series.iloc[-8:-4].sum() if len(capex_series) >= 8 else capex_series.iloc[:4].sum()
    capex_growth = (capex_recent / capex_old - 1) * 100 if capex_old > 0 else None

    roic_recent = roic_series.iloc[-4:].mean()
    roic_old = roic_series.iloc[-8:-4].mean() if len(roic_series) >= 8 else roic_series.iloc[:4].mean()
    roic_change = roic_recent - roic_old if not (np.isnan(roic_recent) or np.isnan(roic_old)) else None

    if capex_growth is None or roic_change is None:
        return {"label": "⚠️ 数据不足", "level": "unknown"}

    # CAPEX 扩张 + ROIC 提升 → 健康扩产
    if capex_growth > 30 and roic_change > 0:
        return {"label": f"🟢 健康扩产（CAPEX+{capex_growth:.0f}%，ROIC↑），产能释放可期", "level": "green"}
    elif capex_growth > 30 and roic_change < -2:
        return {"label": f"🔴 CAPEX 激进但 ROIC 下滑（{roic_change:.1f}pp），警惕周期顶部冲动", "level": "red"}
    elif capex_growth > 30:
        return {"label": f"🟡 扩张期（CAPEX+{capex_growth:.0f}%），关注 ROIC 后续走势", "level": "yellow"}
    elif roic_change > 0:
        # 检查最新季度是否与近4季均值显著偏离（趋势改善但最新值崩塌）
        roic_latest = roic_series.iloc[-1] if len(roic_series) > 0 else None
        if roic_latest is not None and roic_recent > 2 and roic_latest < roic_recent * 0.5:
            return {"label": f"🟡 ROIC近4季趋势改善（+{roic_change:.1f}pp），但最新季度{roic_latest:.1f}%大幅回落，趋势可能逆转", "level": "yellow"}
        return {"label": f"🟢 ROIC提升（+{roic_change:.1f}pp），资本效率持续改善", "level": "green"}
    else:
        return {"label": "⚪ CAPEX 平稳，无明显信号", "level": "yellow"}


# ═══════════════════════════════════════════════
# 探针 3：毛利率韧性
# ═══════════════════════════════════════════════

def probe_margin_resilience(code: str, t_date: str) -> dict:
    """毛利率水平+趋势+与营收的匹配——定价权 vs 价格周期。

    Returns:
        {"label": str, "level": "green"|"yellow"|"red"|"unknown"}
    """
    gm_series = get_quarterly_series(code, "gross_margin", n_quarters=12, t_date=t_date).dropna()
    rev_yoy_series = get_quarterly_series(code, "revenue_yoy", n_quarters=4, t_date=t_date).dropna()

    if len(gm_series) < 8:
        return {"label": "⚠️ 毛利率数据不足", "level": "unknown"}

    gm_recent = gm_series.iloc[-4:].mean()
    gm_old = gm_series.iloc[-8:-4].mean()
    gm_trend = gm_recent - gm_old  # pp change
    gm_std = gm_series.std()       # 波动率
    rev_yoy = rev_yoy_series.iloc[-1] if len(rev_yoy_series) > 0 else 0

    # 高毛利 + 上升 + 高增长 → 强定价权
    if gm_recent > 35 and gm_trend > 0 and rev_yoy > 20:
        return {"label": f"🟢 强定价权（毛利{gm_recent:.0f}%，{gm_trend:+.0f}pp），增长质量高", "level": "green"}
    # 高毛利 + 稳定 → 定价权稳定
    elif gm_recent > 30 and abs(gm_trend) < 2:
        return {"label": f"🟢 定价权稳定（毛利{gm_recent:.0f}%，波动{abs(gm_trend):.1f}pp）", "level": "green"}
    # 毛利下滑 → 警惕
    elif gm_trend < -3:
        return {"label": f"🔴 毛利承压（{gm_trend:+.0f}pp），警惕竞争加剧或成本侵蚀", "level": "red"}
    # 剧烈波动 → 疑似周期
    elif gm_std > 8:
        return {"label": f"🔴 毛利剧烈波动（std={gm_std:.1f}pp），疑似价格周期驱动", "level": "red"}
    else:
        return {"label": f"🟡 毛利正常（{gm_recent:.0f}%，{gm_trend:+.0f}pp），无异常信号", "level": "yellow"}


# ═══════════════════════════════════════════════
# 探针 4：客户集中度（PDF 年报提取）
# ═══════════════════════════════════════════════

def probe_customer_concentration(code: str, t_date: str = None) -> dict:
    """前五大客户销售占比——双击风险 vs 分散韧性。

    数据源：PDF 年报缓存（data/cache/pdf_financials.csv）

    Returns:
        {"label": str, "level": "green"|"yellow"|"red"|"unknown"}
    """
    try:
        from growth_os.pdf_data import get_cached_pdf_data, extract_and_cache
        from growth_os.pdf_download import get_latest_report_path
        pdf = get_cached_pdf_data(code)
        if pdf is None:
            # 缓存缺失，尝试从已下载的PDF中提取
            pdf_path = get_latest_report_path(code, "annual")

            # PDF不存在则先下载
            if not pdf_path:
                logger.info(f"{code}: PDF未下载，从CNINFO获取年报...")
                try:
                    from growth_os.pdf_download import download_reports_batch
                    downloaded = download_reports_batch(code, years=[2023, 2024])
                    if downloaded:
                        pdf_path = get_latest_report_path(code, "annual")
                        logger.info(f"{code}: PDF下载完成: {pdf_path}")
                except Exception as e:
                    logger.warning(f"{code}: PDF下载失败: {e}")

            if pdf_path:
                logger.info(f"{code}: 提取客户集中度 from {pdf_path.name}")
                try:
                    cust = _quick_extract_cust(pdf_path)
                    if cust and (cust.get("top5_ratio") or cust.get("top1_ratio")):
                        # 只存客户集中度到缓存
                        import pandas as pd, os
                        cache_path = "data/cache/pdf_financials.csv"
                        new_row = pd.DataFrame([{
                            "code": code, "report_year": 2023, "category": "annual",
                            "top5_customer_ratio": cust.get("top5_ratio"),
                            "top1_customer_ratio": cust.get("top1_ratio"),
                        }])
                        if os.path.exists(cache_path):
                            existing = pd.read_csv(cache_path, dtype={"code": str})
                            existing = existing[existing["code"] != code]
                            new_row = pd.concat([existing, new_row], ignore_index=True)
                        new_row.to_csv(cache_path, index=False, encoding="utf-8-sig")
                        pdf = {"top5_customer_ratio": cust.get("top5_ratio"),
                               "top1_customer_ratio": cust.get("top1_ratio")}
                except Exception as e:
                    logger.debug(f"{code}: 自动提取失败: {e}")
        if pdf is None:
            return {"label": "⚠️ 客户结构：数据缺失（PDF年报未下载，无法提取前五大客户占比）", "level": "unknown"}

        top5 = pdf.get("top5_customer_ratio")
        top1 = pdf.get("top1_customer_ratio")

        if top5 is None and top1 is None:
            return {"label": "⚠️ 客户结构：年报中未提取到客户集中度数据", "level": "unknown"}

        if top5 is not None:
            ratio = top5
        else:
            ratio = min(top1 * 2.5, 100) if top1 else None  # 估算

        if ratio is None:
            return {"label": "⚠️ 无法解析客户集中度", "level": "unknown"}

        if ratio > 70:
            return {"label": f"🔴 客户高度集中（前五占比{ratio:.0f}%），砍单风险高", "level": "red"}
        elif ratio > 50:
            return {"label": f"🟡 客户集中度偏高（前五占比{ratio:.0f}%）", "level": "yellow"}
        elif ratio > 30:
            return {"label": f"🟡 客户适度集中（前五占比{ratio:.0f}%）", "level": "yellow"}
        else:
            return {"label": f"🟢 客户分散（前五占比{ratio:.0f}%），韧性较强", "level": "green"}

    except ImportError:
        return {"label": "⚠️ PDF 模块不可用", "level": "unknown"}


def _quick_extract_cust(pdf_path) -> dict | None:
    """快速提取客户集中度 — 只用 pdfplumber 文字搜索，跳过 camelot。

    直接搜索关键词「前五名客户」，从附近表格提取占比。
    """
    try:
        import pdfplumber, re
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if not any(kw in text for kw in ["前五名客户", "前五大客户", "客户集中"]):
                    continue
                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue
                    flat = " ".join(str(c) for row in table for c in row if c)
                    if "前五名" not in flat and "客户" not in flat:
                        continue
                    result = {}
                    ratios = []
                    for row in table:
                        if not row:
                            continue
                        row_str = " ".join(str(v) for v in row if v)
                        # 提取百分比
                        pcts = re.findall(r"(\d+\.?\d*)\s*%", row_str)
                        nums = [float(p) for p in pcts if 0 < float(p) <= 100]
                        if any(kw in row_str for kw in ["合计", "总计", "前五"]):
                            ratios.extend(nums)
                        if any(kw in row_str for kw in ["第一名", "客户一", "客户1", "客户 A"]):
                            if nums:
                                result["top1_ratio"] = max(nums)
                    valid = [r for r in ratios if 5 <= r <= 99]
                    if valid:
                        result["top5_ratio"] = max(valid)
                        return result
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════
# 汇总输出
# ═══════════════════════════════════════════════

def _level_to_score(level: str) -> float | None:
    """将探针等级映射为 0-1 连续分值，供 Regime 连续化使用。"""
    return {"green": 1.0, "yellow": 0.5, "red": 0.0}.get(level, None)


def run_all_probes(code: str, t_date: str) -> list[dict]:
    """运行全部增长来源探针，返回列表。

    每个探针含 name/label/level/score 字段。
    score: 0-1 连续分值 (green=1.0, yellow=0.5, red=0.0, unknown=None)
    """
    probes = [
        {"name": "订单领先性", **probe_order_leadership(code, t_date)},
        {"name": "CAPEX效率", **probe_capex_efficiency(code, t_date)},
        {"name": "毛利率韧性", **probe_margin_resilience(code, t_date)},
        {"name": "客户集中度", **probe_customer_concentration(code, t_date)},
    ]
    for p in probes:
        p["score"] = _level_to_score(p["level"])
    return probes


# ═══════════════════════════════════════════════
# 市场层面聚合：为 Regime 连续化提供输入
# ═══════════════════════════════════════════════

def probe_market_health(codes: list[str], t_date: str, sample: int = 100) -> dict:
    """在候选池中抽样，聚合探针信号为市场增长健康度。

    用于辅助 Regime 判断：高健康度时加速退出 DEFENSE，
    低健康度时即使价格恢复也保持谨慎。

    Returns:
        {"health_score": 0-100, "green_pct": float, "red_pct": float,
         "order_green_pct": float, "capex_red_pct": float, "margin_green_pct": float}
    """
    import random
    if len(codes) > sample:
        codes = random.sample(codes, sample)

    counts = {"green": 0, "yellow": 0, "red": 0, "unknown": 0, "total": 0}
    probe_counts = {"order": {"green": 0, "red": 0},
                    "capex": {"green": 0, "red": 0},
                    "margin": {"green": 0, "red": 0}}

    scores = []
    for code in codes:
        try:
            probes = run_all_probes(code, t_date)
            for p in probes:
                level = p["level"]
                counts[level] = counts.get(level, 0) + 1
                counts["total"] += 1
                if p.get("score") is not None:
                    scores.append(p["score"])
                name = p["name"]
                if name == "订单领先性":
                    if level == "green": probe_counts["order"]["green"] += 1
                    if level == "red": probe_counts["order"]["red"] += 1
                elif name == "CAPEX效率":
                    if level == "green": probe_counts["capex"]["green"] += 1
                    if level == "red": probe_counts["capex"]["red"] += 1
                elif name == "毛利率韧性":
                    if level == "green": probe_counts["margin"]["green"] += 1
                    if level == "red": probe_counts["margin"]["red"] += 1
        except Exception:
            counts["unknown"] += 1
            counts["total"] += 1

    n = max(counts["total"], 1)
    green_pct = counts["green"] / n * 100
    red_pct = counts["red"] / n * 100

    # 健康度 = 加权平均分值 × 100（利用 probe_score 连续化）
    if scores:
        health = sum(scores) / len(scores) * 100
    else:
        health = max(0, min(100, 50 + green_pct * 0.8 - red_pct * 1.2))

    return {
        "health_score": round(health, 1),
        "green_pct": round(green_pct, 1),
        "red_pct": round(red_pct, 1),
        "sample_size": n,
        "order_green_pct": round(probe_counts["order"]["green"] / max(n/3, 1) * 100, 1),
        "capex_red_pct": round(probe_counts["capex"]["red"] / max(n/3, 1) * 100, 1),
        "margin_green_pct": round(probe_counts["margin"]["green"] / max(n/3, 1) * 100, 1),
    }
