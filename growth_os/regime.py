"""L0 风格择时门控 — 市场状态判定层。

三通道输入 → 三态输出 → 控制漏斗的 K 值和权重模式。
不修改 L1-L5 打分逻辑，只在漏斗上游加一层开关。

通道A: 成长相对强度 (创业板/沪深300 63日动量)
通道B: 利率边际变化 (10Y国债 63日Δ > 30bp)
通道C: 风格回撤熔断 (创业板指 126日回撤 > 20%)

输出:
  GROWTH_OK   — 正常运作，TopK=30，生命周期权重
  CAUTION     — 单通道触发，TopK=15，加速期降权
  DEFENSE     — 多通道触发，TopK=8，强制成熟期权重
"""
from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from enum import Enum

import akshare as ak
import numpy as np
import pandas as pd
from loguru import logger

warnings.filterwarnings("ignore")


# ═══════════════════════════════════════════════════════════
# 枚举与数据结构
# ═══════════════════════════════════════════════════════════


class RegimeState(Enum):
    GROWTH_OK = "GROWTH_OK"
    CAUTION = "CAUTION"
    RECOVERY = "RECOVERY"
    DEFENSE = "DEFENSE"


@dataclass
class RegimeOutput:
    state: RegimeState
    target_k: int               # 本期入选股票数上限
    weight_mode: str             # "lifecycle" | "defensive" | "maturity_forced"
    l1_strict: bool              # 是否收紧 L1（条件红灯 1 项即淘汰）
    g_proxy_discount: float      # L5 g_proxy 折扣系数 (1.0 = 不打折)
    channel_signals: dict        # 各通道原始信号，用于调试

    @property
    def is_ok(self) -> bool:
        return self.state == RegimeState.GROWTH_OK

    @property
    def is_defense(self) -> bool:
        return self.state == RegimeState.DEFENSE

    @property
    def is_recovery(self) -> bool:
        return self.state == RegimeState.RECOVERY


# ═══════════════════════════════════════════════════════════
# 阈值常量（可调）
# ═══════════════════════════════════════════════════════════

# 通道A: 成长相对强度
GROWTH_REL_WINDOW = 63          # 交易日
GROWTH_REL_WEAK_THRESHOLD = 0.0 # 斜率 < 0 视为弱

# 通道B: 利率
RATE_WINDOW = 63               # 交易日（≈3个月）
RATE_UP_THRESHOLD_BP = 30      # bp

# 通道C: 回撤熔断
DD_WINDOW = 126                 # 交易日（≈6个月）
DD_THRESHOLD = 0.20            # 20%

# 去抖
CONFIRM_PERIODS = 2             # 连续确认期数

# 输出控制
K_OK = 30
K_CAUTION = 15
K_DEFENSE = 8


# ═══════════════════════════════════════════════════════════
# 数据加载（带缓存）
# ═══════════════════════════════════════════════════════════

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache")
_CHINEXT_CACHE: pd.DataFrame | None = None
_HS300_CACHE: pd.DataFrame | None = None
_BOND_CACHE: pd.DataFrame | None = None


def _load_chinext() -> pd.DataFrame:
    """加载创业板指日线，缓存到 CSV。"""
    global _CHINEXT_CACHE
    if _CHINEXT_CACHE is not None:
        return _CHINEXT_CACHE

    cache_path = os.path.join(_CACHE_DIR, "index_399006.csv")
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
        _CHINEXT_CACHE = df
        return df

    df = ak.stock_zh_index_daily(symbol="sz399006")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    os.makedirs(_CACHE_DIR, exist_ok=True)
    df.to_csv(cache_path, index=False)
    _CHINEXT_CACHE = df
    return df


def _load_hs300() -> pd.DataFrame:
    """加载沪深300日线，优先用已有缓存。"""
    global _HS300_CACHE
    if _HS300_CACHE is not None:
        return _HS300_CACHE

    cache_path = os.path.join(_CACHE_DIR, "index_399300.csv")
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
        _HS300_CACHE = df
        return df

    df = ak.stock_zh_index_daily(symbol="sh000300")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    os.makedirs(_CACHE_DIR, exist_ok=True)
    df.to_csv(cache_path, index=False)
    _HS300_CACHE = df
    return df


def _load_bond_10y() -> pd.Series:
    """加载10Y国债收益率日频序列。"""
    global _BOND_CACHE
    if _BOND_CACHE is not None:
        return _BOND_CACHE

    cache_path = os.path.join(_CACHE_DIR, "bond_10y.csv")
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
        s = df.set_index("date")["yield_10y"]
        _BOND_CACHE = s
        return s

    df = ak.bond_zh_us_rate()
    df = df.rename(columns={"日期": "date", "中国国债收益率10年": "yield_10y"})
    df["date"] = pd.to_datetime(df["date"])
    s = df.set_index("date")["yield_10y"].dropna().sort_index()
    os.makedirs(_CACHE_DIR, exist_ok=True)
    s.to_csv(cache_path, header=True)
    _BOND_CACHE = s
    return s


# ═══════════════════════════════════════════════════════════
# 通道信号计算
# ═══════════════════════════════════════════════════════════


def _channel_a_growth_rel(t_date: str) -> tuple[bool, float]:
    """通道A: 成长相对强度。

    创业板/沪深300 63日动量斜率。斜率 < 0 视为成长弱于大盘。

    Returns:
        (triggered, slope_value)
    """
    chinext = _load_chinext()
    hs300 = _load_hs300()
    t_dt = pd.Timestamp(t_date)

    # 截取 t_date 之前的数据
    cy = chinext[chinext["date"] <= t_dt].tail(GROWTH_REL_WINDOW + 1)
    hs = hs300[hs300["date"] <= t_dt].tail(GROWTH_REL_WINDOW + 1)

    if len(cy) < 40 or len(hs) < 40:
        return False, 0.0

    # 计算相对强度曲线: 创业板/沪深300
    common = cy.set_index("date")["close"].reindex(
        hs.set_index("date")["close"].index
    ).dropna()
    hs_aligned = hs.set_index("date")["close"].reindex(common.index).dropna()
    if len(common) < 40:
        return False, 0.0

    rel = common / hs_aligned
    x = np.arange(len(rel))
    slope = np.polyfit(x, rel.values, 1)[0]

    triggered = slope < GROWTH_REL_WEAK_THRESHOLD
    return triggered, round(float(slope), 6)


def _channel_b_rate_pressure(t_date: str) -> tuple[bool, float]:
    """通道B: 利率边际变化。

    10Y国债 63日变动 > +30bp，且当前 > 200日均值。

    Returns:
        (triggered, change_bp)
    """
    bond = _load_bond_10y()
    t_dt = pd.Timestamp(t_date)

    # 找到 t_date 之前最近的一个交易日
    bond_before = bond[bond.index <= t_dt]
    if len(bond_before) < GROWTH_REL_WINDOW + 1:
        return False, 0.0

    recent = bond_before.iloc[-1]
    prior = bond_before.iloc[-(GROWTH_REL_WINDOW + 1)]
    change_bp = (recent - prior) * 100  # 转为 bp

    # 当前需 > 200日均值（避免低利率区间的噪声触发）
    ma200 = bond_before.tail(200).mean()

    triggered = (change_bp > RATE_UP_THRESHOLD_BP) and (recent > ma200)
    return triggered, round(float(change_bp), 1)


def _channel_c_drawdown(t_date: str) -> tuple[bool, float]:
    """通道C: 风格回撤熔断。

    创业板指 126日最大回撤 > 20%，且当前价格 < 63日均线（确认未恢复）。
    价格站上 MA63 视为 V 型反弹确认，回撤信号不予触发。

    Returns:
        (triggered, drawdown_pct)
    """
    chinext = _load_chinext()
    t_dt = pd.Timestamp(t_date)

    cy = chinext[chinext["date"] <= t_dt].tail(max(DD_WINDOW, 63) + 1)
    if len(cy) < 60:
        return False, 0.0

    prices = cy["close"].values
    peak = np.maximum.accumulate(prices[-DD_WINDOW:])
    dd = (prices[-DD_WINDOW:] - peak) / peak
    max_dd = abs(dd.min())

    # 恢复检测：价格站上 63 日均线 → 不触发
    ma63 = np.mean(prices[-63:])
    current_price = prices[-1]
    recovered = current_price > ma63

    triggered = (max_dd > DD_THRESHOLD) and (not recovered)
    return triggered, round(float(max_dd), 3)


# ═══════════════════════════════════════════════════════════
# 去抖状态机
# ═══════════════════════════════════════════════════════════

class _RegimeStateMachine:
    """非对称去抖状态机（v2.2 +RECOVERY）。

    - 进入 DEFENSE：多通道触发时即时生效。
    - DEFENSE → RECOVERY：raw_state 改善为 CAUTION/GROWTH_OK 时进入过渡态。
    - RECOVERY → GROWTH_OK：连续 2 期信号良好（GROWTH_OK/CAUTION）则升级。
    - RECOVERY → DEFENSE：raw_state 重新触发 DEFENSE 则跌回。
    - RECOVERY 超时：连续 4 期后强制升级 GROWTH_OK。
    """

    def __init__(self):
        self.current = RegimeState.GROWTH_OK
        self.pending = RegimeState.GROWTH_OK
        self.counter = 0
        self.recovery_periods = 0

    def update(self, raw_state: RegimeState) -> RegimeState:
        # 多通道升级到 DEFENSE：即时生效
        if raw_state == RegimeState.DEFENSE and self.current != RegimeState.DEFENSE:
            self.current = RegimeState.DEFENSE
            self.pending = RegimeState.DEFENSE
            self.counter = 0
            self.recovery_periods = 0
            return self.current

        # 已在 DEFENSE 中 → 信号改善 → 进入 RECOVERY
        if self.current == RegimeState.DEFENSE:
            if raw_state in (RegimeState.GROWTH_OK, RegimeState.CAUTION):
                self.current = RegimeState.RECOVERY
                self.pending = RegimeState.RECOVERY
                self.counter = 0
                self.recovery_periods = 1
                return self.current
            return self.current

        # 已在 RECOVERY 中
        if self.current == RegimeState.RECOVERY:
            self.recovery_periods += 1

            # 跌回 DEFENSE：信号重新恶化
            if raw_state == RegimeState.DEFENSE:
                self.current = RegimeState.DEFENSE
                self.recovery_periods = 0
                return self.current

            # 超时保护：4期后强制升级
            if self.recovery_periods >= 4:
                self.current = RegimeState.GROWTH_OK
                self.recovery_periods = 0
                return self.current

            # 连续 2 期信号良好 → 升级 GROWTH_OK
            if raw_state in (RegimeState.GROWTH_OK, RegimeState.CAUTION):
                self.counter += 1
                if self.counter >= 2:
                    self.current = RegimeState.GROWTH_OK
                    self.counter = 0
                    self.recovery_periods = 0
                    return self.current
            else:
                self.counter = 0

            return self.current

        # CAUTION ↔ GROWTH_OK：标准去抖
        if raw_state == self.current:
            self.counter = 0
            self.pending = self.current
            return self.current

        if raw_state == self.pending:
            self.counter += 1
        else:
            self.pending = raw_state
            self.counter = 1

        if self.counter >= CONFIRM_PERIODS:
            self.current = self.pending
            self.counter = 0

        return self.current


_state_machine = _RegimeStateMachine()


def reset_state_machine():
    """重置去抖状态机（回测开始时调用）。"""
    global _state_machine
    _state_machine = _RegimeStateMachine()


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════


def compute_regime(t_date: str) -> RegimeOutput:
    """计算当前市场状态。

    Args:
        t_date: 数据日期 YYYYMMDD

    Returns:
        RegimeOutput 包含状态和对应的操作参数。
    """
    # 计算三通道信号
    a_triggered, a_slope = _channel_a_growth_rel(t_date)
    b_triggered, b_bp = _channel_b_rate_pressure(t_date)
    c_triggered, c_dd = _channel_c_drawdown(t_date)

    signals = {
        "A_growth_rel": {"triggered": a_triggered, "value": a_slope},
        "B_rate": {"triggered": b_triggered, "value": b_bp},
        "C_drawdown": {"triggered": c_triggered, "value": c_dd},
    }

    triggered = [k for k, v in signals.items() if v["triggered"]]

    # 规则: A+C 或 B+C 或 A+B+C → DEFENSE
    #       任意单通道 → CAUTION
    #       无触发 → GROWTH_OK
    has_a = a_triggered
    has_b = b_triggered
    has_c = c_triggered

    if (has_a and has_c) or (has_b and has_c) or (has_a and has_b):
        raw_state = RegimeState.DEFENSE
    elif has_a or has_b or has_c:
        raw_state = RegimeState.CAUTION
    else:
        raw_state = RegimeState.GROWTH_OK

    # 去抖
    state = _state_machine.update(raw_state)

    # 根据状态生成操作参数
    if state == RegimeState.DEFENSE:
        target_k = K_DEFENSE
        weight_mode = "maturity_forced"
        l1_strict = True
        g_discount = 0.5
    elif state == RegimeState.RECOVERY:
        target_k = K_CAUTION       # Top15 成长 + 防御资产
        weight_mode = "lifecycle"  # 恢复期用正常权重
        l1_strict = False
        g_discount = 0.8           # 轻微折扣，不过度惩罚
    elif state == RegimeState.CAUTION:
        target_k = K_CAUTION
        weight_mode = "defensive"
        l1_strict = True
        g_discount = 0.7
    else:
        target_k = K_OK
        weight_mode = "lifecycle"
        l1_strict = False
        g_discount = 1.0

    return RegimeOutput(
        state=state,
        target_k=target_k,
        weight_mode=weight_mode,
        l1_strict=l1_strict,
        g_proxy_discount=g_discount,
        channel_signals=signals,
    )


# ═══════════════════════════════════════════════════════════
# 工具：回测辅助
# ═══════════════════════════════════════════════════════════


def compute_regime_for_backtest(t_date: str) -> RegimeOutput:
    """回测用入口（自动重置去抖状态 + 每次调用 compute_regime）。

    季度回测场景：每次调用都是新的筛选点，去抖 StateMachine 保持跨期记忆。
    """
    return compute_regime(t_date)


def regime_summary(outputs: list[RegimeOutput]) -> dict:
    """汇总一组 RegimeOutput 的统计信息。

    Args:
        outputs: 回测中每期的 RegimeOutput 列表。

    Returns:
        {"GROWTH_OK": n, "CAUTION": n, "DEFENSE": n,
         "trigger_rates": {"A": pct, "B": pct, "C": pct}}
    """
    state_counts = {s: 0 for s in [RegimeState.GROWTH_OK, RegimeState.CAUTION, RegimeState.DEFENSE]}
    channel_triggers = {"A_growth_rel": 0, "B_rate": 0, "C_drawdown": 0}
    n = len(outputs)

    for out in outputs:
        state_str = out.state
        state_counts[state_str] = state_counts.get(state_str, 0) + 1
        for ch, sig in out.channel_signals.items():
            if sig["triggered"]:
                channel_triggers[ch] = channel_triggers.get(ch, 0) + 1

    return {
        "state_distribution": {
            k.value: v for k, v in state_counts.items()
        },
        "trigger_rates": {
            ch: round(cnt / n * 100, 1) if n > 0 else 0
            for ch, cnt in channel_triggers.items()
        },
        "n_periods": n,
    }


# ═══════════════════════════════════════════════════════════
# CLI 快速诊断
# ═══════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="L0 风格择时门控 — 快速诊断")
    parser.add_argument("--date", type=str, default="20250630",
                        help="诊断日期 YYYYMMDD")
    parser.add_argument("--history", action="store_true",
                        help="打印近期通道指标值")
    args = parser.parse_args()

    out = compute_regime(args.date)
    print(f"\n  L0 Regime 诊断: {args.date}")
    print(f"  状态: {out.state.value}")
    print(f"  TopK: {out.target_k}")
    print(f"  权重模式: {out.weight_mode}")
    print(f"  L1严格: {out.l1_strict}")
    print(f"  g_proxy折扣: {out.g_proxy_discount}")
    print(f"  通道信号:")
    for ch, sig in out.channel_signals.items():
        flag = "🚩" if sig["triggered"] else "✅"
        print(f"    {flag} {ch}: {sig['value']}")

    if args.history:
        chinext = _load_chinext()
        bond = _load_bond_10y()
        print(f"\n  创业板指: {len(chinext)} 行, "
              f"范围 {chinext['date'].min().date()} ~ {chinext['date'].max().date()}")
        print(f"  10Y国债: {len(bond)} 行, "
              f"范围 {bond.index.min().date()} ~ {bond.index.max().date()}")


if __name__ == "__main__":
    main()
