"""Lifecycle Research Layer v1 — 研究任务分配器（Step 5）。

定位:
    从"股票列表"升级为"研究任务分配器"。
    不改 score/ranking/portfolio，只增加研究标签。

内部状态 → 业务语言:
    L0 → Ignore
    L1 → Early Discovery（变化发生，市场未确认）
    L2 → Confirmation（市场开始确认）
    L3 → Consensus（一致预期，风险区）
    L5 → Recovery Watch（错杀恢复，基本面未坏）

输出结构 (Research Card 字段):
    lifecycle_state: L1/L2/L3/L5/L0
    research_stage: 业务语言
    research_priority: A/B/C/IGNORE
    drivers: 探针理由 (为什么进入)
    risks: 风险
    radar: growth_radar | recovery_radar | watch

用法 (双轨, 不改变现有输出):
    from growth_os.lifecycle_research import LifecycleResearchLayer
    layer = LifecycleResearchLayer(ind_map)
    cards = layer.annotate(result_df, t_date)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from growth_os.state_machine import (
    InvestmentStateModel, PARADIGM_MAP, PRIORITY, STATE_LABELS,
)
from growth_os.l5_recovery import L5RecoveryEngine
from growth_os.expectation_state import ExpectationStateEngine
from screener import compute_rps60

# Lifecycle v3: L × E Opportunity Matrix (EXPECTATION_AUDIT 实证)
# 返回 (priority, 说明)
OPPORTUNITY_MATRIX = {
    # (L, E档) -> priority
    ("L1", "E0"): ("A", "变化发生+市场忽略(预期差窗口)"),
    ("L1", "E1"): ("A", "变化发生+少数关注"),
    ("L1", "E2"): ("C", "变化真实但市场已定价⚠️"),
    ("L1", "E3"): ("D", "一致预期(故事已消化)"),
    ("L2", "E0"): ("A", "确认中但市场仍忽略"),
    ("L2", "E1"): ("B", "确认中+关注启动"),
    ("L2", "E2"): ("C", "确认+已定价"),
    ("L5", "E0"): ("A", "错杀+市场恐慌(最佳窗口)"),
    ("L5", "E1"): ("A", "错杀+关注初现"),
    ("L5", "E2"): ("B", "恢复已部分交易⚠️"),
    ("L3", "E2"): ("C", "一致预期区"),
    ("L3", "E3"): ("D", "过度交易区"),
}
_DEFAULT_PRI = ("C", "矩阵未覆盖")

# 探针/财务字段预热（性能：避免逐股全表过滤）
_PREWARM_FIELDS = [
    "contract_liabilities", "revenue_yoy", "capex_cash", "roic",
    "gross_margin", "net_profit_yoy", "operating_cash_flow",
]


def prewarm_financial_cache(t_date: str):
    """预热 growth_os.data 季度缓存（一次过滤 + groupby，探针全部命中）。"""
    import growth_os.data as gdata
    from data_governance import filter_available_reports

    if t_date in gdata._snapshot_cache:
        return
    # 必须用 growth_os.data 自己的加载器: 填充其 _tdx_cache (探针依赖)
    raw = gdata.load_tdx_financials()
    avail = filter_available_reports(raw, t_date)
    avail["code"] = avail["code"].astype(str).str.zfill(6)
    gdata._snapshot_cache[t_date] = (
        avail.sort_values("report_date_str").groupby("code").tail(1).copy()
    )
    for code, g in avail.groupby("code"):
        gs = g.sort_values("report_date_str")
        for f in _PREWARM_FIELDS:
            if f in gs.columns:
                gdata._quarterly_cache[(code, f, t_date)] = (
                    gs.set_index("report_date_str")[f].astype(float)
                )

# 内部状态 → 业务语言
STAGE_LABELS = {
    "L0": "Ignore",
    "L1": "Early Discovery",
    "L2": "Confirmation",
    "L3": "Consensus",
    "L5": "Recovery Watch",
}

RADAR_MAP = {
    "L1": "growth_radar",
    "L2": "growth_radar",
    "L3": "watch",
    "L5": "recovery_radar",
    "L0": "watch",
}


class LifecycleResearchLayer:
    """研究标签层：批量标注生命周期状态 + 研究优先级。"""

    def __init__(self, ind_map: dict, rps_threshold_low: float = 40.0,
                 rps_threshold_high: float = 70.0):
        self.ind_map = ind_map
        self.sm = InvestmentStateModel(
            rps_threshold_low=rps_threshold_low,
            rps_threshold_high=rps_threshold_high,
            ind_map=ind_map,
        )
        self.l5 = L5RecoveryEngine(ind_map=ind_map)
        self.expect = ExpectationStateEngine()

    def annotate(self, df: pd.DataFrame, t_date: str,
                 hist_rps_max: dict = None) -> pd.DataFrame:
        """给候选 DataFrame 加生命周期标签列。

        df: 需含 code 列（候选池）。
        返回: 原 df + lifecycle_state/research_stage/research_priority/
              radar/drivers/risks 列。
        """
        out = df.copy()
        codes = out["code"].astype(str).str.zfill(6).tolist()

        # 0. 预热财务缓存（性能关键）
        prewarm_financial_cache(t_date)

        # 1. RPS（PIT，行业截面）
        rps_map = compute_rps60(codes, t_date, self.ind_map)

        # 2. L5 判定（需要历史 RPS 峰值）
        l5_results = {
            r.code: r for r in self.l5.scan(codes, t_date, rps_map=rps_map,
                                            hist_rps_map=hist_rps_max)
        }

        # 3. 逐票状态 (v3: L 状态 + E 状态 + Opportunity Matrix priority)
        expect_map = self.expect.classify_many(codes, t_date, rps_map)
        states, stages, pris, radars = [], [], [], []
        drivers, risks = [], []
        e_states, e_notes = [], []
        for c in codes:
            rps = rps_map.get(c, np.nan)
            l5r = l5_results.get(c)
            e = expect_map.get(c)
            e_st = e.state if e else "E0"
            e_states.append(e_st)
            if l5r is not None and l5r.state.startswith("L5"):
                state = "L5"
                drv = [f"错杀恢复: {x}" for x in l5r.reasons[:3]]
                rk = l5r.risks[:3]
            else:
                s = self.sm.evaluate(c, t_date, rps=rps)
                state = s.state
                drv = s.reasons[:3]
                rk = s.risks[:3]
            # v3 矩阵: (L, E) → priority
            pri, note = OPPORTUNITY_MATRIX.get((state, e_st), _DEFAULT_PRI)
            if l5r is not None and l5r.state.startswith("L5"):
                # L5 引擎自带优先级作为基线, 矩阵修正
                if pri != "A":
                    pri = l5r.priority if l5r.priority != "A" else pri
            states.append(state)
            stages.append(STAGE_LABELS.get(state, state))
            pris.append(pri)
            radars.append(RADAR_MAP.get(state, "watch"))
            drivers.append("; ".join(drv) if drv else "")
            risks.append("; ".join(rk) if rk else "")
            e_notes.append(note)

        out["lifecycle_state"] = states
        out["expectation_state"] = e_states
        out["research_stage"] = stages
        out["research_priority"] = pris
        out["radar"] = radars
        out["drivers"] = drivers
        out["risks"] = risks
        out["priority_note"] = e_notes
        return out
