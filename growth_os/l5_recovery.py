"""L5 Mispricing Recovery Engine v1 — 错杀恢复研究状态识别器。

定位 (L5_MISPRICING_MODEL.md):
    不是买入信号, 不是评分因子。
    回答: "这家公司是否值得研究'为什么跌'"。

判定链 (四层):
    Layer 1: 过去被市场认可 (排除长期垃圾股)
    Layer 2: 发生错误定价 (快速回撤 / RPS崩塌 / PE压缩, 三选二)
    Layer 3: 基本面未破坏 (探针 red<=1 + 收入未加速恶化 + 利润未连续恶化)
    Layer 4: 行业范式白名单 (v1: cycle_manufacturing + consumer)

输出等级:
    L5-A: 历史确认 + 杀跌明显 + 基本面完整 → 最高研究优先级
    L5-B: 历史确认 + 杀跌, 但基本面信息不足 → 需人工
    REJECT: 不满足

验证协议 (Train/Test 分离):
    Train 2022-2023 定参数 / Test 2024-2025 独立验证 (tools/l5_audit.py)
    验收: L5-L0>5% / 恢复概率>50% / 错误率<15% / 胜率>55%
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from pit.market import MarketData
from pit.financial import FinancialData
from growth_os.state_machine import PARADIGM_MAP
from growth_os.growth_probes import (
    probe_order_leadership, probe_capex_efficiency, probe_margin_resilience,
)

# v1 行业白名单 (证据: L1 周期制造 +5.5pp 有效, tech_growth 无效)
L5_ALLOWED_PARADIGMS = {"cycle_manufacturing", "consumer"}

# v1 默认阈值 (Train 期可调)
DEFAULTS = {
    "rps_confirm": 70,        # Layer1: 历史 RPS 曾 ≥70 = 曾被确认
    "ret_60d": -0.20,         # Layer2: 60日收益 < -20%
    "dd_120d": -0.25,         # Layer2: 120日高点回撤 < -25%
    "rps_collapse": 30,       # Layer2: 历史 RPS 峰值 - 当前 RPS > 30
    "pe_pct_high": 0.70,      # Layer2: 历史 PE 分位曾 > 70%
    "pe_pct_low": 0.40,       # Layer2: 当前 PE 分位 < 40%
    "probe_red_max": 1,       # Layer3: red 探针数 ≤ 1
    "rev_decline_acc": -0.05, # Layer3: 收入同比恶化加速阈值 (两期变化 < -5pp)
}


@dataclass
class L5Result:
    code: str
    state: str                    # "L5-A" | "L5-B" | "REJECT"
    priority: str                 # "A" | "B" | "IGNORE"
    reasons: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)  # 各层判定明细 (审计用)

    def to_dict(self) -> dict:
        return {
            "code": self.code, "state": self.state, "priority": self.priority,
            "reasons": self.reasons, "risks": self.risks,
        }


class L5RecoveryEngine:
    """错杀恢复识别器 v1。"""

    def __init__(self, ind_map: dict = None, thresholds: dict = None):
        self._ind_map = ind_map or {}
        self._mkt = MarketData()
        self._fin = FinancialData()
        self.t = {**DEFAULTS, **(thresholds or {})}

    # ---------- 数据采集 (全部 PIT) ----------
    def _price_df(self, code: str, t_date: str) -> pd.DataFrame:
        return self._mkt.as_of(code, t_date)

    def _returns(self, df: pd.DataFrame, days: int) -> Optional[float]:
        if df is None or len(df) < days + 1:
            return None
        close = df["close"]
        p0 = close.iloc[-days - 1]
        p1 = close.iloc[-1]
        return float(p1 / p0 - 1) if p0 > 0 else None

    def _dd_from_high(self, df: pd.DataFrame, days: int) -> Optional[float]:
        if df is None or len(df) < 2:
            return None
        window = df["close"].iloc[-days:]
        high = float(window.max())
        cur = float(df["close"].iloc[-1])
        return float(cur / high - 1) if high > 0 else None

    def _pe_pct(self, df: pd.DataFrame, window: int = 252) -> Optional[tuple]:
        """返回 (当前PE, 当前分位, 历史最高分位)。"""
        if "peTTM" not in df.columns:
            return None
        pe = df["peTTM"].dropna()
        pe = pe[(pe > 0) & (pe < 500)]
        if len(pe) < 60:
            return None
        cur_pe = float(pe.iloc[-1])
        hist = pe.iloc[-window:]
        cur_pct = float((hist < cur_pe).mean())
        # 历史最高分位: 过去一年内 PE 曾处的分位 (以更长历史为基准)
        base = pe.iloc[-window * 2:]
        max_pct = float((base < hist.max()).mean()) if len(base) > 0 else cur_pct
        return cur_pe, cur_pct, max_pct

    def _revenue_trend(self, code: str, t_date: str) -> Optional[str]:
        """收入趋势: "stable" | "declining" | "accelerating_decline"。"""
        s = self._fin.quarterly_series(code, "revenue_yoy", t_date, 6)
        if len(s) < 4:
            return None
        vals = s.dropna().values.astype(float)
        if len(vals) < 4:
            return None
        last = vals[-1]
        prev = vals[-2]
        # 加速恶化: 已为负且继续变差
        if last < 0 and (last - prev) < self.t["rev_decline_acc"]:
            return "accelerating_decline"
        if last < 0:
            return "declining"
        return "stable"

    def _profit_trend(self, code: str, t_date: str) -> Optional[str]:
        """利润趋势: "stable" | "deteriorating"。连续两期利润同比下行。"""
        s = self._fin.quarterly_series(code, "net_profit_yoy", t_date, 4)
        if len(s) < 3:
            return None
        vals = s.dropna().values.astype(float)
        if len(vals) < 3:
            return None
        if vals[-1] < 0 and vals[-2] < 0 and vals[-1] <= vals[-2]:
            return "deteriorating"
        return "stable"

    # ---------- 主判定 ----------
    def evaluate(self, code: str, t_date: str,
                 current_rps: Optional[float] = None,
                 hist_rps_max: Optional[float] = None) -> L5Result:
        """单只判定。

        current_rps / hist_rps_max: 由外部批量预计算传入 (RPS 需行业截面,
        单股无法自算)。缺省时 RPS 条件降级为跳过 (不阻塞)。
        """
        detail = {}
        reasons, risks = [], []

        # --- Layer 4: 行业白名单 ---
        paradigm = PARADIGM_MAP.get(self._ind_map.get(code, ""), "other")
        if paradigm not in L5_ALLOWED_PARADIGMS:
            return L5Result(code, "REJECT", "IGNORE",
                            [], [f"行业范式 {paradigm} 不在 L5 v1 白名单"],
                            {"paradigm": paradigm})
        detail["paradigm"] = paradigm

        # --- Layer 1: 历史确认 ---
        confirmed = False
        if hist_rps_max is not None and hist_rps_max >= self.t["rps_confirm"]:
            confirmed = True
            reasons.append(f"历史 RPS 峰值 {hist_rps_max:.0f} ≥ {self.t['rps_confirm']:.0f} (曾被市场确认)")
        if not confirmed:
            return L5Result(code, "REJECT", "IGNORE", [],
                            ["历史未被市场确认 (RPS 从未 ≥70 或数据不足)"],
                            {**detail, "layer1": False})
        detail["layer1"] = True

        # --- Layer 2: 错误定价 (三选二) ---
        df = self._price_df(code, t_date)
        mispricing_hits = []
        detail["layer2"] = {}

        r60 = self._returns(df, 60)
        dd120 = self._dd_from_high(df, 120)
        if r60 is not None and r60 < self.t["ret_60d"]:
            mispricing_hits.append("快速回撤")
            detail["layer2"]["ret_60d"] = round(r60, 4)
        if dd120 is not None and dd120 < self.t["dd_120d"]:
            mispricing_hits.append("高点回撤")
            detail["layer2"]["dd_120d"] = round(dd120, 4)

        if current_rps is not None and hist_rps_max is not None:
            if hist_rps_max - current_rps > self.t["rps_collapse"]:
                mispricing_hits.append("RPS崩塌")
                detail["layer2"]["rps_collapse"] = hist_rps_max - current_rps

        pe_info = self._pe_pct(df)
        if pe_info is not None:
            _, cur_pct, max_pct = pe_info
            detail["layer2"]["pe_cur_pct"] = round(cur_pct, 3)
            detail["layer2"]["pe_max_pct"] = round(max_pct, 3)
            if max_pct > self.t["pe_pct_high"] and cur_pct < self.t["pe_pct_low"]:
                mispricing_hits.append("PE压缩")

        if len(mispricing_hits) < 2:
            return L5Result(code, "REJECT", "IGNORE",
                            [], [f"错误定价条件不足 ({len(mispricing_hits)}/3)"],
                            {**detail, "layer2_hits": mispricing_hits})
        reasons.append("错误定价: " + " + ".join(mispricing_hits))

        # --- Layer 3: 基本面未破坏 ---
        p1 = probe_order_leadership(code, t_date)
        p2 = probe_capex_efficiency(code, t_date)
        p3 = probe_margin_resilience(code, t_date)
        reds = [p["label"] for p in (p1, p2, p3) if p["level"] == "red"]
        detail["probe_reds"] = reds

        rev = self._revenue_trend(code, t_date)
        profit = self._profit_trend(code, t_date)
        detail["revenue"] = rev
        detail["profit"] = profit

        basic_intact = True
        if len(reds) > self.t["probe_red_max"]:
            basic_intact = False
            risks.append(f"探针恶化 ({len(reds)} 个 red): " + "; ".join(reds))
        if rev == "accelerating_decline":
            basic_intact = False
            risks.append("收入同比加速恶化")
        if profit == "deteriorating":
            basic_intact = False
            risks.append("利润连续两期恶化")

        if not basic_intact:
            return L5Result(code, "REJECT", "IGNORE",
                            reasons, risks, {**detail, "layer3": False})

        # --- 输出等级 ---
        if len(reds) == 0 and rev == "stable" and profit == "stable":
            state, pri = "L5-A", "A"
        else:
            state, pri = "L5-B", "B"
        reasons.append("基本面未破坏 (探针/收入/利润)")

        return L5Result(code, state, pri, reasons, risks, {**detail, "layer3": True})

    def scan(self, codes: list[str], t_date: str,
             rps_map: dict = None, hist_rps_map: dict = None) -> list[L5Result]:
        """批量判定。rps_map: {code: 当前RPS}, hist_rps_map: {code: 历史RPS峰值}。"""
        out = []
        for c in codes:
            out.append(self.evaluate(c, t_date,
                                     rps_map.get(c) if rps_map else None,
                                     hist_rps_map.get(c) if hist_rps_map else None))
        return out
