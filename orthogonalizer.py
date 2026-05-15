"""分块对称正交化 — 消除块内信号共线性"""
import numpy as np


def _pairwise_cov(signals: dict[str, np.ndarray]) -> np.ndarray:
    """Pairwise-complete 协方差矩阵。k×k。"""
    names = list(signals.keys())
    k = len(names)
    cov = np.zeros((k, k))
    for i in range(k):
        for j in range(i, k):
            si = signals[names[i]]
            sj = signals[names[j]]
            mask = ~np.isnan(si) & ~np.isnan(sj)
            if mask.sum() < 10:
                cov[i, j] = 0.0
            else:
                cov[i, j] = np.cov(si[mask], sj[mask])[0, 1]
            cov[j, i] = cov[i, j]
    return cov


def symmetric_orthogonalize(
    signals: dict[str, np.ndarray],
    blocks: list[list[str]],
) -> dict[str, np.ndarray]:
    """
    分块对称正交化。每块内EVD正交，块间保留原始相关。

    Args:
        signals: {name: N×1 array}
        blocks: [["S3","S4"], ["S5","S7"]]
    Returns:
        正交化因子 {name: N×1 array}
    """
    result = {}
    for block in blocks:
        block_signals = {s: signals[s] for s in block if s in signals}
        if len(block_signals) < 2:
            for s in block_signals:
                result[s] = block_signals[s].copy()
            continue

        names = list(block_signals.keys())
        k = len(names)
        S = np.column_stack([block_signals[n] for n in names])
        cov = _pairwise_cov(block_signals)
        eigvals, eigvecs = np.linalg.eigh(cov)
        eigvals = np.maximum(eigvals, 1e-10)
        D_inv_sqrt = np.diag(1.0 / np.sqrt(eigvals))
        L = eigvecs @ D_inv_sqrt @ eigvecs.T
        F = S @ L
        for i, name in enumerate(names):
            result[name] = F[:, i]

    return result
