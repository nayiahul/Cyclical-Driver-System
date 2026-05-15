"""风险中性化 — 横截面OLS取残差"""
import numpy as np
import pandas as pd
from loguru import logger


def neutralize(
    signals: dict[str, np.ndarray],
    risk_factors: pd.DataFrame,
) -> dict[str, np.ndarray]:
    """
    对每个信号做横截面回归，剥除风险因子影响。

    Args:
        signals: {name: N×1 array}，NaN保留
        risk_factors: N×4 DataFrame with columns [beta, size, volatility, illiquidity]

    Returns:
        残差因子 {name: N×1 array}，NaN填入0
    """
    rf = risk_factors.values  # N×4
    result = {}
    for name, s_arr in signals.items():
        residual = np.full_like(s_arr, 0.0, dtype=float)
        mask = ~np.isnan(s_arr)
        if mask.sum() < 30:
            result[name] = residual
            continue

        y = s_arr[mask]
        X = rf[mask]
        try:
            XtX = X.T @ X
            XtX_inv = np.linalg.inv(XtX + np.eye(X.shape[1]) * 1e-6)
            beta = XtX_inv @ X.T @ y
            residual[mask] = y - X @ beta
        except np.linalg.LinAlgError:
            residual[mask] = y

        result[name] = residual

    logger.info(f"风险中性化完成: {len(signals)} signals")
    return result
