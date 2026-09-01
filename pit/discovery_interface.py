"""Discovery Engine 接口定义（Gate 3 阶段：只定义，不实现）。

背景:
    Baseline A 审计发现当前系统 = Confirmation 强 + Discovery 弱。
    三引擎架构共识: Discovery(发现) → Confirmation(确认) → Valuation(估值)。
    Gate 4+ 完成 PIT 后，Phase 2 先验证 H0(三引擎互补)/H1(认知差)，
    验证通过后才实现本接口。

原则:
    1. 本文件只定义接口与数据契约，不包含任何实现
    2. 所有输入必须经 PIT 层（pit/）获得
    3. 输出是"研究候选证据"，不是"买入信号"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pit.contracts import DataPoint


@dataclass
class DiscoverySignal:
    """单一发现信号（带 lineage）。"""

    code: str
    signal_type: str          # "cycle_inflection" | "earnings_inflection" | "industry_cycle" | "event_change"
    strength: float           # 0-1 信号强度
    direction: str            # "up" | "down" | "flat"
    as_of: str                # 信号计算时点 (YYYYMMDD)
    evidence: list[DataPoint] = field(default_factory=list)  # 支撑证据（带数据来源）
    description: str = ""


@dataclass
class DiscoveryResult:
    """个股发现层输出。"""

    code: str
    as_of: str
    has_change: bool          # 是否有值得研究的变化
    lifecycle_stage: str      # L0-L5（见 INVESTMENT_HYPOTHESIS.md）
    signals: list[DiscoverySignal] = field(default_factory=list)
    need_manual_verify: list[str] = field(default_factory=list)  # 待人工验证项


class DiscoveryProvider:
    """发现引擎接口。

    职责: 回答"哪里正在发生重要变化？"
    输入: PIT 层数据（FinancialData / MarketData / IndustryData）
    输出: DiscoveryResult（研究候选证据）
    """

    def evaluate(self, code: str, t_date: str) -> DiscoveryResult:
        """评估单只股票的变化状态。"""
        raise NotImplementedError("Phase 3 实现（先经 Phase 2 H0/H1 验证）")

    def scan(self, codes: list[str], t_date: str) -> list[DiscoveryResult]:
        """批量扫描（研究池候选生成）。"""
        raise NotImplementedError("Phase 3 实现")


# ---- 未来信号组件契约（实现时逐步填充） ----

class CycleSignal:
    """周期变化信号: 库存/价格/供需（产业数据）。"""

    def evaluate(self, code: str, t_date: str) -> Optional[DiscoverySignal]:
        raise NotImplementedError


class EarningsInflection:
    """盈利拐点信号: 单季同比改善/环比改善/毛利率拐点（改进版 S1/S2）。"""

    def evaluate(self, code: str, t_date: str) -> Optional[DiscoverySignal]:
        raise NotImplementedError


class IndustryCycle:
    """产业周期: 行业动量 + 宏观驱动（PMI/出口/资本开支）。"""

    def evaluate(self, code: str, t_date: str) -> Optional[DiscoverySignal]:
        raise NotImplementedError


class EventChange:
    """事件变化: 财报/订单/政策/机构调研（Phase 3 事件层）。"""

    def evaluate(self, code: str, t_date: str) -> Optional[DiscoverySignal]:
        raise NotImplementedError
