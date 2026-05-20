"""自动主题动量 — RPS60 跳升检测

用申万三级行业内 RPS60 中位数的近期跳升作为"主题热度"代理。
替代手工维护的战略标签，消除后验强化偏差。

输出: diagnostics/theme_momentum_YYYYMM.csv
"""
import os
from collections import defaultdict

import numpy as np
import pandas as pd


def detect_hot_themes(rps_scores: dict, industry_map: dict,
                      l3_map: dict, threshold: float = 15) -> pd.DataFrame:
    """
    检测 RPS60 跳升的三级行业。

    Args:
        rps_scores: {code: RPS60 percentile}
        industry_map: {code: L1 industry}
        l3_map: {code: SW L3 name}
        threshold: 行业 RPS60 中位数超过此阈值判定为"热主题"

    Returns:
        DataFrame with columns: l3_name, l1_name, median_rps, n_stocks, is_hot
    """
    # 三级行业 RPS60 中位数
    l3_rps = defaultdict(list)
    for code, rps in rps_scores.items():
        l3 = l3_map.get(code, "")
        if l3:
            l3_rps[l3].append(rps)

    rows = []
    for l3_name, rps_list in l3_rps.items():
        median_rps = np.median(rps_list)
        # 找该行业的 L1
        l1 = ""
        for code in l3_map:
            if l3_map[code] == l3_name:
                l1 = industry_map.get(code, "")
                break
        rows.append({
            "l3_name": l3_name,
            "l1_name": l1,
            "median_rps": round(median_rps, 1),
            "n_stocks": len(rps_list),
            "is_hot": median_rps > threshold,
        })

    df = pd.DataFrame(rows).sort_values("median_rps", ascending=False)
    return df


def save_themes(df: pd.DataFrame, date_str: str):
    out_dir = "diagnostics"
    os.makedirs(out_dir, exist_ok=True)
    path = f"{out_dir}/theme_momentum_{date_str}.csv"
    df.to_csv(path, index=False)
    return path
