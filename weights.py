"""因子IR动态权重"""
import numpy as np
from scipy.stats import spearmanr
from loguru import logger


def compute_rank_ic(factor_values: np.ndarray, returns: np.ndarray) -> float:
    """单期 Rank IC (Spearman)"""
    mask = ~np.isnan(factor_values) & ~np.isnan(returns)
    if mask.sum() < 30:
        return 0.0
    ic, _ = spearmanr(factor_values[mask], returns[mask])
    return ic if not np.isnan(ic) else 0.0


def compute_ir(ic_series: list[float]) -> float:
    """IR = mean(IC) / std(IC)"""
    if len(ic_series) < 12 or np.std(ic_series) == 0:
        return 0.0
    return np.mean(ic_series) / np.std(ic_series)


def compute_factor_weights(
    factor_ic: dict[str, list[float]],
    cold_start: bool = False,
) -> dict[str, float]:
    """IR → 归一化权重。冷启动或IR全≤0 → 等权"""
    if cold_start:
        n = len(factor_ic)
        return {name: 1.0 / n for name in factor_ic}

    irs = {name: compute_ir(ics) for name, ics in factor_ic.items()}
    pos_irs = {name: max(0, ir) for name, ir in irs.items()}
    total = sum(pos_irs.values())

    if total == 0:
        logger.info("所有因子 IR ≤ 0，回退等权")
        n = len(factor_ic)
        return {name: 1.0 / n for name in factor_ic}

    return {name: ir / total for name, ir in pos_irs.items()}


class IRWeightManager:
    """管理因子IC历史序列和滚动IR权重"""

    def __init__(self, factor_names: list[str], window: int = 36):
        self.factor_names = factor_names
        self.window = window
        self.ic_history: dict[str, list[float]] = {n: [] for n in factor_names}
        self.months_elapsed = 0

    def update(self, factor_values: dict[str, np.ndarray], forward_returns: np.ndarray):
        """记录一个月IC值"""
        for name in self.factor_names:
            if name in factor_values:
                ic = compute_rank_ic(factor_values[name], forward_returns)
                self.ic_history[name].append(ic)
        self.months_elapsed += 1

    def get_weights(self) -> dict[str, float]:
        """当前IR权重（过去window个月IC）"""
        recent_ic = {
            name: ics[-self.window:] if len(ics) >= self.window else ics
            for name, ics in self.ic_history.items()
        }
        cold_start = self.months_elapsed < self.window
        return compute_factor_weights(recent_ic, cold_start=cold_start)


class CycleIRWeightManager:
    """周期分层IR权重管理器。按BULL/STRUCT/BEAR分层存储IC历史。"""

    def __init__(self, factor_names: list[str], window: int = 36):
        self.factor_names = factor_names
        self.window = window
        self.months_elapsed = 0
        self.ic_history = {"BULL": {}, "STRUCT": {}, "BEAR": {}}
        for regime in self.ic_history:
            self.ic_history[regime] = {n: [] for n in factor_names}
        self.regime_history: list[str] = []

    def update(self, factor_values: dict[str, np.ndarray], forward_returns: np.ndarray, regime: str):
        """记录一个月IC，按Regime分层"""
        from weights import compute_rank_ic
        for name in self.factor_names:
            if name in factor_values:
                ic = compute_rank_ic(factor_values[name], forward_returns)
                self.ic_history[regime][name].append(ic)
        self.regime_history.append(regime)
        self.months_elapsed += 1

    def get_weights(self, regime: str) -> dict[str, float]:
        """当前Regime对应的IR权重，样本不足回退全周期"""
        from weights import compute_factor_weights

        if self.months_elapsed < self.window:
            n = len(self.factor_names)
            return {name: 1.0 / n for name in self.factor_names}

        regime_ic = self.ic_history.get(regime, {})
        if all(len(ics) >= 12 for ics in regime_ic.values()):
            return compute_factor_weights(regime_ic, cold_start=False)

        # 回退全周期
        all_ic = {}
        for name in self.factor_names:
            combined = []
            for r_ics in self.ic_history.values():
                combined.extend(r_ics.get(name, []))
            all_ic[name] = combined[-self.window:]
        return compute_factor_weights(all_ic, cold_start=False)
