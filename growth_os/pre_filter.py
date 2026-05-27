"""预过滤器 — 三层候选池漏斗。

第一层：基础清洗（可投资性，不涉及成长判断）
第二层：Growth Signal Gate（多路径 OR，不排序不截断）
第三层：主漏斗（现有 L1-L5，由调用方执行）

核心原则：预过滤器只排除明显不合格的，不替漏斗做选择。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from growth_os.config import PRE_FILTER as CFG


# ═══════════════════════════════════════════════
# 第一层：基础清洗
# ═══════════════════════════════════════════════

def basic_clean(df: pd.DataFrame) -> pd.DataFrame:
    """只做可投资性判断，不涉及成长定义。

    排除：ST、数据缺失、金融地产、极端微型股。
    """
    n0 = len(df)

    mask = pd.Series(True, index=df.index)

    # 1. 财报数据完整性
    for field in CFG["require_fields"]:
        if field in df.columns:
            mask &= df[field].notna()
            mask &= ~df[field].isin([np.inf, -np.inf])

    # 2. 排除金融/地产（商业模式不同）
    exclude_l1 = set(CFG["exclude_sectors_l1"])
    if "industry_l1" in df.columns:
        mask &= ~df["industry_l1"].isin(exclude_l1)

    # 3. 排除无行业分类的
    if "industry_l3" in df.columns:
        mask &= df["industry_l3"].notna()
        mask &= df["industry_l3"] != ""

    # 4. 排除极端微型股（市值 < 2亿，壳价值以下）
    if "market_cap" in df.columns:
        mask &= df["market_cap"] >= CFG.get("min_market_cap", 2.0)

    # 5. 排除负营收（数据异常）
    if "revenue" in df.columns:
        mask &= df["revenue"] > 0

    df_out = df[mask].copy()
    n1 = len(df_out)

    logger.info(f"[L1 基础清洗] {n0} → {n1} 只 "
                f"（排除 {n0 - n1}: 数据缺失/金融地产/微型股/负营收）")
    return df_out


# ═══════════════════════════════════════════════
# 第二层：Growth Signal Gate（多路径 OR）
# ═══════════════════════════════════════════════

def compute_growth_signals(df: pd.DataFrame) -> pd.DataFrame:
    """计算成长信号，不做加权求和，各自独立判断。

    返回带布尔列的 DataFrame：
      - pass_route_a: 行业相对增速突出
      - pass_route_b: 订单/需求先行
      - pass_route_c: 资本效率+定价权
      - pass_route_d: 困境反转迹象
    """
    df = df.copy()
    n = len(df)

    # --- Route A: 行业相对增速突出 ---
    # 营收增速在同行业内排前 60%（不是绝对值，不同行业基准不同）
    if "revenue_yoy" in df.columns and "industry_l3" in df.columns:
        df["rev_yoy_pct_industry"] = df.groupby("industry_l3")["revenue_yoy"].transform(
            lambda x: x.rank(pct=True)
        )
        df["pass_route_a"] = df["rev_yoy_pct_industry"] > CFG["route_a"]["revenue_pct_threshold"]
    else:
        df["pass_route_a"] = False

    # --- Route B: 订单/需求先行（行业相对） ---
    # 合同负债占总资产比例在同行业内排前 60%
    if "contract_liabilities" in df.columns and "total_assets" in df.columns and "industry_l3" in df.columns:
        df["_cl_ratio"] = df["contract_liabilities"].fillna(0) / df["total_assets"].replace(0, np.nan).fillna(1)
        df["cl_ratio_pct_industry"] = df.groupby("industry_l3")["_cl_ratio"].transform(
            lambda x: x.rank(pct=True)
        )
        df["pass_route_b"] = df["cl_ratio_pct_industry"] > CFG["route_b"]["cl_ratio_pct_threshold"]
    else:
        df["pass_route_b"] = False

    # --- Route C: 资本效率（行业相对） ---
    # ROIC 在同行业内排前 50%
    if "roic" in df.columns and "industry_l3" in df.columns:
        df["roic_pct_industry"] = df.groupby("industry_l3")["roic"].transform(
            lambda x: x.rank(pct=True)
        )
        df["pass_route_c"] = df["roic_pct_industry"] > CFG["route_c"]["roic_pct_threshold"]
    else:
        df["pass_route_c"] = False

    # --- Route D: 困境反转迹象 ---
    # 毛利率 > 0 AND 存货周转天数 < 行业中位数（库存消化中）
    has_gm_positive = df["gross_margin"].fillna(0) > 0 if "gross_margin" in df.columns else pd.Series(False, index=df.index)
    if "inventory_days" in df.columns and "industry_l3" in df.columns:
        df["inv_days_pct_industry"] = df.groupby("industry_l3")["inventory_days"].transform(
            lambda x: x.rank(pct=True, ascending=False)  # 库存越低越好（反转时库存下降）
        )
        # 库存分位高 = 库存相对少（反转信号）+ 有定价权 + 合同负债存在
        has_cl = df["contract_liabilities"].fillna(0) > 0 if "contract_liabilities" in df.columns else pd.Series(False, index=df.index)
        df["pass_route_d"] = (df["inv_days_pct_industry"] > 0.5) & has_gm_positive & has_cl
    else:
        df["pass_route_d"] = False

    # --- 汇总 ---
    df["_pass_gate"] = (
        df["pass_route_a"]
        | df["pass_route_b"]
        | df["pass_route_c"]
        | df["pass_route_d"]
    )

    route_counts = {
        "A(行业增速)": df["pass_route_a"].sum(),
        "B(订单先行)": df["pass_route_b"].sum(),
        "C(资本效率)": df["pass_route_c"].sum(),
        "D(困境反转)": df["pass_route_d"].sum(),
    }
    logger.info(f"[L2 成长信号] 各路通过: {route_counts}")

    return df


def apply_growth_gate(df: pd.DataFrame) -> pd.DataFrame:
    """应用成长信号门控：至少一条路径通过。"""
    df = compute_growth_signals(df)
    n_before = len(df)
    df_out = df[df["_pass_gate"]].copy()
    n_after = len(df_out)

    # 输出每条路径的贡献
    for route in ["pass_route_a", "pass_route_b", "pass_route_c", "pass_route_d"]:
        if route in df_out.columns:
            # 统计仅靠这一条路径通过的股票数（互斥）
            other_routes = [r for r in ["pass_route_a", "pass_route_b",
                                        "pass_route_c", "pass_route_d"] if r != route]
            exclusive = df_out[df_out[route] & ~df_out[other_routes].any(axis=1)]
            if len(exclusive) > 0:
                route_name = route.replace("pass_route_", "")
                logger.debug(f"  仅{route_name}: {len(exclusive)} 只")

    logger.info(f"[L2 成长信号门] {n_before} → {n_after} 只 "
                f"（排除 {n_before - n_after}: 四路径全无成长迹象）")
    return df_out


# ═══════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════

def pre_filter(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """三层预过滤主函数。

    Args:
        df: load_growth_data() 返回的全市场 DataFrame

    Returns:
        (candidates_df, stats_dict)
        candidates_df: 通过预过滤的候选池
        stats_dict: 每层统计信息
    """
    stats = {"input": len(df)}

    # 第一层：基础清洗
    df = basic_clean(df)
    stats["after_l1"] = len(df)

    # 第二层：成长信号门控
    df = apply_growth_gate(df)
    stats["after_l2"] = len(df)

    # 清理内部列（保留分位列供优先级排序使用）
    pass_cols = [c for c in df.columns if c.startswith("pass_route_")]
    internal_cols = [c for c in df.columns if c.startswith("_")]
    df = df.drop(columns=[c for c in pass_cols + internal_cols if c in df.columns])

    logger.info(f"[预过滤完成] {stats['input']} → {stats['after_l1']} → {stats['after_l2']}")

    return df, stats


# ═══════════════════════════════════════════════
# 可选的优先级排序（不截断，只决定执行顺序）
# ═══════════════════════════════════════════════

def sort_by_relevance(df: pd.DataFrame, max_candidates: int = None) -> pd.DataFrame:
    """按成长相关性排序，不截断，只决定漏斗执行顺序。

    Args:
        df: 预过滤后的候选池
        max_candidates: 如果指定，仅返回前 N 只（用于快速模式）

    排序逻辑：营收行业分位(50%) + ROIC行业分位(50%)
    全部基于截面数据，不做逐只漏斗运算。
    """
    if "rev_yoy_pct_industry" not in df.columns:
        return df.head(max_candidates) if max_candidates else df

    df = df.copy()
    df["_priority"] = (
        df["rev_yoy_pct_industry"].fillna(0.5) * 0.5
        + df.get("roic_pct_industry", pd.Series(0.5, index=df.index)).fillna(0.5) * 0.5
    )
    df = df.sort_values("_priority", ascending=False)
    df = df.drop(columns=["_priority"])

    logger.info(f"[优先级排序] 候选池 {len(df)} 只已按成长相关性排序")

    if max_candidates and len(df) > max_candidates:
        logger.warning(f"[快速模式] 仅取前 {max_candidates} 只进入主漏斗 "
                       f"（全量 {len(df)} 只，建议非快速模式全跑）")
        return df.head(max_candidates)

    return df
