"""因子相关性矩阵 — 检测景气因子是否坍缩为单一因子。

输出: diagnostics/factor_corr_YYYYMM.csv
"""
import os

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def compute_factor_correlation(scores: dict[str, pd.Series]) -> pd.DataFrame:
    """
    Args:
        scores: {"RPS60": series, "S1": series, ...} — 每个因子一个 Series (index=code)

    Returns:
        DataFrame — pairwise Spearman 相关矩阵
    """
    # 合并所有因子值
    names = list(scores.keys())
    arrays = {}
    for name in names:
        s = scores[name]
        if isinstance(s, dict):
            s = pd.Series(s)
        arrays[name] = s

    df = pd.DataFrame(arrays)
    valid = df.dropna()
    if len(valid) < 30:
        return pd.DataFrame()

    corr = pd.DataFrame(index=names, columns=names, dtype=float)
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if i > j:
                continue
            if i == j:
                corr.loc[a, b] = 1.0
                continue
            common = df[[a, b]].dropna()
            if len(common) < 30:
                corr.loc[a, b] = np.nan
                corr.loc[b, a] = np.nan
            else:
                r, _ = spearmanr(common[a], common[b])
                corr.loc[a, b] = round(r, 4)
                corr.loc[b, a] = round(r, 4)

    return corr


def save_correlation(corr: pd.DataFrame, date_str: str):
    """保存到 diagnostics/ 目录。"""
    out_dir = "diagnostics"
    os.makedirs(out_dir, exist_ok=True)
    path = f"{out_dir}/factor_corr_{date_str}.csv"
    corr.to_csv(path)
    return path


def highlight_concentration(corr: pd.DataFrame, threshold: float = 0.65) -> list[str]:
    """标记高相关因子对 (>threshold)。"""
    warnings = []
    names = list(corr.columns)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            r = corr.iloc[i, j]
            if not np.isnan(r) and abs(r) > threshold:
                warnings.append(f"{names[i]} ↔ {names[j]}: r={r:.3f}")
    return warnings
