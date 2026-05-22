"""个股波动率降权 — 高波动股是回撤放大器。

60日收益率标准差在行业内前10% → composite ×0.9。
"""
import numpy as np
import pandas as pd


def compute_volatility_penalty(codes: list[str],
                                industry_map: dict,
                                price_loader) -> dict[str, float]:
    """
    Returns {code: penalty_coef} — 高波动股 0.9, 其余 1.0。
    """
    # 计算每只股票的60日波动率
    vols = {}
    for code in codes:
        df = price_loader(code)
        if len(df) < 60:
            continue
        ret = df["close"].pct_change().dropna().iloc[-60:]
        if len(ret) < 40:
            continue
        vols[code] = ret.std()

    if not vols:
        return {}

    # 行业内分位
    ind_vols = {}
    for code, vol in vols.items():
        ind = industry_map.get(code, "未知")
        if ind not in ind_vols:
            ind_vols[ind] = []
        ind_vols[ind].append((code, vol))

    penalty = {}
    for ind, items in ind_vols.items():
        if len(items) < 5:
            for code, _ in items:
                penalty[code] = 1.0
            continue
        sorted_vols = sorted([v for _, v in items])
        p90 = sorted_vols[int(len(sorted_vols) * 0.9)]
        for code, vol in items:
            penalty[code] = 0.9 if vol >= p90 else 1.0

    return penalty
