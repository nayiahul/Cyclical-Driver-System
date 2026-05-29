"""预计算行业分位表 — O(n)构建,O(1)查表。

v3.0 Sprint 6: 解决 L2 行业相对化 O(n²) 性能瓶颈。
用 df.groupby("industry_l3").rank(pct=True) 一次性生成所有分位,
后续评分直接 code→pct 查表。
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from loguru import logger


# 全局分位表: {industry: {metric: {code: pct(0-1)}}}
_PCT_CACHE: dict = {}


def build_percentile_table(df: pd.DataFrame, t_date: str = "") -> dict:
    """预计算行业分位表。一次 O(n) 扫描,后续 O(1) 查表。

    对 L2 相关指标在行业内做百分位排名:
      - expense_leverage: 费用率越低越好(反向排名)
      - gross_margin: 毛利率越高越好
      - rd_intensity: 研发强度越高越好

    Args:
        df: 包含 code/industry_l3 + 各指标列的 DataFrame
        t_date: 可选,用于缓存键

    Returns:
        {industry: {metric: {code: pct}}}
    """
    global _PCT_CACHE
    cache_key = t_date or "latest"
    if cache_key in _PCT_CACHE:
        return _PCT_CACHE[cache_key]

    if "industry_l3" not in df.columns:
        logger.warning("industry_l3 列缺失,无法构建行业分位表")
        return {}

    pct_table: dict = {}
    grouped = df.groupby("industry_l3", observed=True)

    for industry, group in grouped:
        n = len(group)
        if n < 5:  # 行业太小,不排名
            continue

        entry = {}
        codes = group["code"].tolist()

        # 1. gross_margin (越高越好 → rank pct)
        if "gross_margin" in group.columns:
            ranks = group["gross_margin"].rank(pct=True)
            entry["gross_margin"] = dict(zip(codes, ranks.fillna(0.5)))

        # 1b. expense_ratio: (销售+管理)/营收 (越低越好 → 反向rank)
        sell = group.get("selling_expense", pd.Series(0, index=group.index)).fillna(0)
        admin = group.get("admin_expense", pd.Series(0, index=group.index)).fillna(0)
        rev = group["revenue"].replace(0, np.nan)
        exp_ratio = (sell + admin) / rev * 100
        ranks = (-exp_ratio).rank(pct=True)  # 负值排序=越低越好
        entry["expense_ratio"] = dict(zip(codes, ranks.fillna(0.5)))

        # 2. rd_intensity (越高越好)
        if "rd_expense" in group.columns and "revenue" in group.columns:
            rd_vals = group["rd_expense"].fillna(0) / group["revenue"].replace(0, 1) * 100
            ranks = rd_vals.rank(pct=True)
            entry["rd_intensity"] = dict(zip(codes, ranks.fillna(0.5)))

        # 3. contract_liabilities growth (越高越好 — 用 snapshot 已有字段)
        if "contract_liabilities" in group.columns and "total_assets" in group.columns:
            cl_ratio = group["contract_liabilities"].fillna(0) / group["total_assets"].replace(0, 1)
            ranks = cl_ratio.rank(pct=True)
            entry["contract_liab_ratio"] = dict(zip(codes, ranks.fillna(0.5)))

        # 4. revenue_yoy (越高越好 — 已有字段)
        if "revenue_yoy" in group.columns:
            ranks = group["revenue_yoy"].rank(pct=True)
            entry["revenue_yoy"] = dict(zip(codes, ranks.fillna(0.5)))

        pct_table[industry] = entry

    _PCT_CACHE[cache_key] = pct_table
    logger.info(f"行业分位表构建完成: {len(pct_table)} 个行业")
    return pct_table


def get_pct(pct_table: dict, industry: str, metric: str, code: str) -> float:
    """O(1) 查表获取分位。缺失→0.5(中位数,无区分)。"""
    ind = pct_table.get(industry, {})
    met = ind.get(metric, {})
    return met.get(code, 0.5)
