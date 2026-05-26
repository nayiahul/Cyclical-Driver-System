"""Regime 连续化原型 — 离散状态机 → 0-100% 成长仓位。

复用现有三通道信号函数（regime.py），输出连续仓位而非状态标签。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from growth_os.regime import (
    _channel_a_growth_rel,
    _channel_b_rate_pressure,
    _channel_c_drawdown,
    _load_chinext,
    reset_state_machine,
)


class ContinuousRegime:
    """连续仓位计算器。

    每期输出 0-100 的成长仓位比例，剩余配置防御资产。
    三通道影响幅度各约 ±30，中性起点 50，平滑后钳位 [0,100]。
    """

    def __init__(self, smooth: float = 0.5, max_delta: float = 50):
        self.smooth = smooth      # 动量平滑系数（0.5=快速响应）
        self.max_delta = max_delta  # 单次仓位变动上限
        self.prev = 50.0          # 起始中性
        self._history: list[dict] = []

    def compute(self, t_date: str) -> float:
        """计算指定日期的成长仓位 (0-100)。"""
        # --- 三通道连续信号 ---
        _, a_slope = _channel_a_growth_rel(t_date)    # -0.01 ~ +0.01
        _, b_bp = _channel_b_rate_pressure(t_date)     # -50 ~ +100 bp
        _, c_dd = _channel_c_drawdown(t_date)           # 0.0 ~ 0.50

        # --- 映射到仓位贡献（各通道约 ±30） ---
        # A: 成长相对强度。扩大灵敏度
        a_score = np.clip(a_slope * 8000, -35, 35)

        # B: 利率压力
        b_score = -np.clip(max(0, b_bp) * 0.25, 0, 25)

        # C: 回撤状态。深度压制，恢复后正向
        # 自行检测恢复（价格 vs MA63），不依赖 channel_c 的布尔值
        chinext = _load_chinext()
        t_dt = pd.Timestamp(t_date)
        cy = chinext[chinext["date"] <= t_dt].tail(126)
        if len(cy) >= 63:
            prices = cy["close"].values
            ma63 = np.mean(prices[-63:])
            current = prices[-1]
            recovered = current > ma63

            if recovered:
                c_score = 20                        # 已恢复：正向贡献
            elif c_dd > 0.25:
                c_score = -35                       # 深度回撤：强力压制
            elif c_dd > 0.15:
                c_score = -20                       # 中度回撤
            else:
                c_score = -5                        # 轻微回撤
        else:
            c_score = -5

        # --- 基础仓位 ---
        raw = 50.0 + a_score + b_score + c_score
        raw = max(0.0, min(100.0, raw))

        # --- 平滑 ---
        smoothed = self.prev * self.smooth + raw * (1 - self.smooth)
        delta = np.clip(smoothed - self.prev, -self.max_delta, self.max_delta)
        exposure = self.prev + delta
        exposure = max(0.0, min(100.0, exposure))

        self.prev = exposure
        self._history.append({
            "date": t_date, "raw": raw, "exposure": exposure,
            "a": round(a_score, 1), "b": round(b_score, 1), "c": round(c_score, 1),
        })
        return exposure

    @property
    def history_df(self) -> pd.DataFrame:
        return pd.DataFrame(self._history)


def run_validation():
    """离线验证：输出 2022-2025 仓位曲线与 v2.1 状态对比。"""
    from growth_os.backtest import _get_quarterly_dates

    dates = _get_quarterly_dates("20220101", "20250331")
    cutoff = pd.Timestamp("20250331") - pd.DateOffset(months=12)
    dates = [d for d in dates if pd.Timestamp(d) <= cutoff]

    cr = ContinuousRegime()
    reset_state_machine()

    print(f"{'日期':<12} {'A斜率':>8} {'B利率bp':>8} {'C回撤':>8} {'原始':>6} {'仓位':>6}")
    print("-" * 56)
    for d in dates:
        exp = cr.compute(d)
        h = cr._history[-1]
        print(f"{d:<12} {h['a']:>+7.1f} {h['b']:>+7.1f} {h['c']:>+7.1f} "
              f"{h['raw']:>5.0f}% {exp:>5.0f}%")

    print(f"\n关键时点检查:")
    df = cr.history_df
    print(f"  2022Q1-Q3 仓位: {df[df['date'].isin(['20220331','20220630','20220930'])]['exposure'].values}")
    print(f"  2024Q1-Q2 仓位: {df[df['date'].isin(['20240331','20240630'])]['exposure'].values}")


if __name__ == "__main__":
    run_validation()
