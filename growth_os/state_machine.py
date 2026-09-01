"""Investment State Model v1 — 机会状态识别层。

基于 Discovery Signal Audit v1 的证据:
  Discovery 高 + RPS 低 → 未来 6 月 +1.6% (vs 低+低 -0.5%, 增量 +2.1pp)
  Discovery 高 + RPS 高 → -1.6% (预期差消失)

设计原则:
  1. 不修改 compute_composite / 任何评分
  2. 只生成状态标签 (L0-L5) + 研究优先级 + 理由
  3. 输入全部来自 PIT 层 (pit/)
  4. 状态机分层替代权重相加

用法:
    sm = InvestmentStateModel()
    result = sm.evaluate(code, t_date)   # 单只
    results = sm.scan(codes, t_date)     # 批量
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from pit.market import MarketData
from growth_os.growth_probes import (
    probe_order_leadership,
    probe_capex_efficiency,
    probe_margin_resilience,
)
from screener import compute_rps60
from pit.financial import FinancialData

# 探针等级 → 分数
LEVEL_SCORE = {"green": 1.0, "yellow": 0.5, "red": 0.0, "unknown": np.nan}

# 状态定义 (L0-L5, 与 INVESTMENT_HYPOTHESIS.md 一致)
STATE_LABELS = {
    "L0": "无变化",
    "L1": "Early Discovery（变化发生, 市场未确认）",
    "L2": "Inflection Confirmation（变化确认中）",
    "L3": "Market Confirmed（市场已确认, 预期差收窄）",
    "L4": "Fully Priced（估值透支）",
    "L5": "错杀恢复（逻辑未坏, 短期事件下跌）",
}

# 研究优先级
PRIORITY = {"L1": "A", "L5": "A", "L2": "B", "L3": "C", "L4": "D", "L0": "IGNORE"}

# v2: 行业范式映射 (INDUSTRY_PARADIGM_MAP.md, 2026-09-01 实证)
PARADIGM_MAP = {
    # 周期制造: L1 优先 (核心研究区, L1-L0 = +5.5pp)
    "有色金属": "cycle_manufacturing", "基础化工": "cycle_manufacturing",
    "机械设备": "cycle_manufacturing", "钢铁": "cycle_manufacturing",
    "煤炭": "cycle_manufacturing", "石油石化": "cycle_manufacturing",
    "建筑材料": "cycle_manufacturing",
    # 科技成长: 探针状态机不适用 (L1-L0 = -1.6pp)
    "电子": "tech_growth", "通信": "tech_growth", "计算机": "tech_growth",
    "传媒": "tech_growth", "国防军工": "tech_growth",
    # 消费: L1 弱有效 (+2.8pp)
    "食品饮料": "consumer", "医药生物": "consumer", "家用电器": "consumer",
    "纺织服饰": "consumer", "商贸零售": "consumer", "农林牧渔": "consumer",
    "社会服务": "consumer", "美容护理": "consumer",
    # 防御: L2 确认优先 (+2.2pp)
    "银行": "defensive", "非银金融": "defensive", "公用事业": "defensive",
    "交通运输": "defensive", "房地产": "defensive",
}


@dataclass
class StateResult:
    code: str
    state: str                    # L0-L5
    priority: str                 # A/B/C/D/IGNORE
    discovery_score: float        # 0-1
    rps: float                    # 0-100
    reasons: list = field(default_factory=list)
    risks: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "code": self.code, "state": self.state,
            "priority": self.priority,
            "discovery_score": round(self.discovery_score, 3),
            "rps": round(self.rps, 1),
            "reasons": self.reasons, "risks": self.risks,
        }


class InvestmentStateModel:
    """机会状态识别层（v1）。"""

    def __init__(self, rps_threshold_low: float = 40.0,
                 rps_threshold_high: float = 70.0,
                 disc_threshold: float = 0.5,
                 ind_map: dict = None):
        self.rps_low = rps_threshold_low
        self.rps_high = rps_threshold_high
        self.disc_thr = disc_threshold
        self._ind_map = ind_map or {}
        self._mkt = MarketData()
        self._fin = FinancialData()

    def _paradigm(self, code: str) -> str:
        """行业范式: SW1 → PARADIGM_MAP。"""
        ind = self._ind_map.get(code, "")
        return PARADIGM_MAP.get(ind, "other")

    # ---- Discovery 综合分（复用 3 个财务探针）----
    def _discovery_score(self, code: str, t_date: str) -> tuple[float, list, list]:
        p1 = probe_order_leadership(code, t_date)
        p2 = probe_capex_efficiency(code, t_date)
        p3 = probe_margin_resilience(code, t_date)
        scores = [LEVEL_SCORE.get(p["level"], np.nan) for p in (p1, p2, p3)]
        valid = [s for s in scores if not np.isnan(s)]
        if not valid:
            return np.nan, [], ["探针数据不足"]
        disc = float(np.mean(valid))

        reasons = []
        risks = []
        for label, p in [("订单", p1), ("CAPEX", p2), ("毛利", p3)]:
            if p["level"] == "green":
                reasons.append(p["label"])
            elif p["level"] == "red":
                risks.append(p["label"])
        return disc, reasons, risks

    # ---- RPS（PIT 截断）----
    def _rps(self, code: str, t_date: str, ind_map: dict = None) -> float:
        # 单只股票 RPS 需要行业分位 → 批量场景由 scan() 预计算传入
        return np.nan

    # ---- 状态机 v2: 行业范式参数化 ----
    def _classify(self, code: str, disc: float, rps: float,
                  reasons: list, risks: list) -> StateResult:
        if np.isnan(disc):
            return StateResult(code, "L0", "IGNORE", np.nan, rps,
                               reasons, ["Discovery 数据不足"])

        paradigm = self._paradigm(code)

        # 科技成长: 探针状态机不适用 (实证 L1-L0 = -1.6pp)
        if paradigm == "tech_growth":
            return StateResult(code, "L0", "IGNORE", disc, rps,
                               reasons, ["tech_growth 范式: 探针状态机不适用, 需技术/订单类信号"])

        # 防御行业: 确认后优先 (L2, 实证 +2.2pp)
        if paradigm == "defensive":
            if disc >= self.disc_thr and rps >= self.rps_low:
                return StateResult(code, "L2", "B", disc, rps, reasons, risks)
            return StateResult(code, "L0", "IGNORE", disc, rps, reasons, risks)

        # cycle_manufacturing / consumer / other: L1 优先 (实证 +5.5pp / +2.8pp)
        if disc >= self.disc_thr:
            if rps < self.rps_low:
                state, pri = "L1", "A"
            elif rps < self.rps_high:
                state, pri = "L2", "B"
            else:
                state, pri = "L3", "C"
        else:
            state, pri = "L0", "IGNORE"
        return StateResult(code, state, pri, disc, rps, reasons, risks)

    def evaluate(self, code: str, t_date: str, rps: Optional[float] = None,
                 ind_map: dict = None) -> StateResult:
        disc, reasons, risks = self._discovery_score(code, t_date)
        if rps is None:
            # 单只场景: 无行业分位 → RPS 用 NaN (状态机按 L0 处理)
            return self._classify(code, disc, np.nan, reasons, risks)
        return self._classify(code, disc, rps, reasons, risks)

    def scan(self, codes: list[str], t_date: str, ind_map: dict) -> list[StateResult]:
        """批量扫描: 预计算 RPS 后逐只分类。"""
        rps_map = compute_rps60(codes, t_date, ind_map)
        out = []
        for c in codes:
            rps = rps_map.get(c, np.nan)
            disc, reasons, risks = self._discovery_score(c, t_date)
            out.append(self._classify(c, disc, rps, reasons, risks))
        return out
