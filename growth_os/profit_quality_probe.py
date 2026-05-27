"""利润质量归因探针 — 拆解扣非利润与归母利润的差异来源。

当 deducted_vs_revenue 触发红灯（扣非增速远差于营收增速）时，
自动检查：费用率恶化 / 信用减值拖累 / 非经常性收益桥。

不参与综合评分，仅输出归因标签。数据源：TDX财务快照。
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from loguru import logger

from growth_os.data import get_financial_snapshot, get_quarterly_series


def probe_profit_quality(code: str, t_date: str) -> dict:
    """扣非利润恶化归因分析。

    检查四项可能原因：
    1. 费用刚性：营收下降但费用未同步缩减
    2. 信用减值拖累：大额信用减值损失侵蚀利润
    3. 非经常性桥：归母利润被非经常性收益撑住
    4. 未知：以上均不成立，标注待提取科目

    Returns:
        {"label": str, "level": "red"|"yellow"|"green",
         "causes": list[str], "has_issue": bool}
    """
    snap = get_financial_snapshot(t_date)
    row = snap[snap["code"] == code]
    if row.empty:
        return {"label": "数据不足", "level": "unknown", "causes": [], "has_issue": False}
    row = row.iloc[0]

    causes = []
    has_serious = False

    # ---- 基准数据 ----
    revenue = row.get("revenue")
    if revenue is None or pd.isna(revenue) or revenue <= 0:
        return {"label": "营收数据缺失", "level": "unknown", "causes": [], "has_issue": False}

    deduct_yoy = row.get("deducted_profit_yoy")
    rev_yoy = row.get("revenue_yoy")
    if deduct_yoy is None or rev_yoy is None or pd.isna(deduct_yoy) or pd.isna(rev_yoy):
        return {"label": "增速数据缺失", "level": "unknown", "causes": [], "has_issue": False}

    # 只有扣非增速显著差于营收增速时才做归因
    gap = abs(deduct_yoy - rev_yoy) if deduct_yoy < rev_yoy else 0
    if gap < 10:
        return {"label": "扣非与营收增速差距较小，无明显利润质量问题", "level": "green",
                "causes": [], "has_issue": False}

    # ---- 检查1: 费用率变化 ----
    # 比较近4季 vs 前4季的费用率
    expense_fields = {
        "selling_expense": "销售费用率",
        "admin_expense": "管理费用率",
        "rd_expense": "研发费用率",
        "finance_expense": "财务费用率",
    }
    expense_issues = []
    for field, name in expense_fields.items():
        series = get_quarterly_series(code, field, n_quarters=8, t_date=t_date).dropna()
        if len(series) < 6:
            continue
        rev_series = get_quarterly_series(code, "revenue_q", n_quarters=8, t_date=t_date).dropna()
        if len(rev_series) < 6:
            continue
        common = series.index.intersection(rev_series.index)
        if len(common) < 6:
            continue
        recent_ratio = series.loc[common[-4:]].sum() / rev_series.loc[common[-4:]].sum()
        older_ratio = series.loc[common[-8:-4]].sum() / rev_series.loc[common[-8:-4]].sum()
        delta = (recent_ratio - older_ratio) * 100
        if delta > 1.5:  # 费用率上升超过1.5pp
            expense_issues.append(f"{name}+{delta:.1f}pp")

    if expense_issues:
        causes.append(f"费用刚性：{'，'.join(expense_issues)}（营收降但费用未同步缩减）")
        has_serious = True

    # ---- 检查2: 信用减值拖累 ----
    credit_imp = row.get("credit_impairment_loss")
    if credit_imp is not None and not pd.isna(credit_imp):
        # credit_imp 单位是万元，revenue 单位是元
        imp_ratio = abs(credit_imp) * 10000 / revenue * 100
        if imp_ratio > 1.0:  # 信用减值/营收 > 1%
            causes.append(f"信用减值拖累（减值/营收={imp_ratio:.1f}%）")
            if imp_ratio > 3.0:
                has_serious = True

    # ---- 检查3: 非经常性桥 ----
    net_yoy = row.get("net_profit_yoy")
    if net_yoy is not None and not pd.isna(net_yoy):
        bridge = net_yoy - deduct_yoy  # 归母增速 - 扣非增速 > 0 说明非经常性在抬轿
        if bridge > 10:
            causes.append(f"非经常性收益支撑归母利润（归母增速{net_yoy:.0f}% vs 扣非增速{deduct_yoy:.0f}%，桥≈{bridge:.0f}pp）")
            if bridge > 30:
                has_serious = True

    # ---- 检查4: 扣非利润率 vs 净利率 背离 ----
    net_margin_q = get_quarterly_series(code, "net_margin", n_quarters=4, t_date=t_date).dropna()
    deduct_q = get_quarterly_series(code, "deducted_profit_q", n_quarters=4, t_date=t_date).dropna()
    rev_q = get_quarterly_series(code, "revenue_q", n_quarters=4, t_date=t_date).dropna()
    if len(net_margin_q) >= 2 and len(deduct_q) >= 2 and len(rev_q) >= 2:
        common = deduct_q.index.intersection(rev_q.index)
        if len(common) >= 2:
            deduct_margin_recent = deduct_q.loc[common[-2:]].sum() / rev_q.loc[common[-2:]].sum() * 100
            net_margin_recent = net_margin_q.iloc[-2:].mean()
            if net_margin_recent > 8 and deduct_margin_recent < 5:
                causes.append(f"净利率{net_margin_recent:.1f}%依赖非经常性（扣非利润率仅{deduct_margin_recent:.1f}%）")
                has_serious = True

    # ---- 汇总 ----
    if not causes:
        causes.append("扣非下滑原因待进一步分析（可能涉及资产减值/投资收益/公允价值变动等未提取科目）")
    else:
        # 估算归因覆盖率：已知来源占总缺口的大致比例
        explained_pp = 0
        for c in causes:
            if "费用刚性" in c:
                explained_pp += 5  # rough estimate: expense ratio changes
            if "信用减值" in c:
                explained_pp += 3
            if "非经常性" in c:
                explained_pp += 10
        if explained_pp > 0 and gap > explained_pp * 1.5:
            causes.append(f"⚠️ 以上归因仅解释部分缺口(~{explained_pp}pp)，剩余约{gap-explained_pp:.0f}pp可能来自资产减值损失、其他收益变动、毛利率绝对额变化等未提取科目，建议人工复核年报附注")

    level = "red" if has_serious else "yellow"
    label = " | ".join(causes)
    return {"label": label, "level": level, "causes": causes, "has_issue": has_serious}
