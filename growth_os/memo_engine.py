"""Investment Memo Engine v1 — 研究决策结构化层 (Step 6-B-1)。

定位: 不是文本生成器, 是决策接口。
输入: 仅 PIT 层 + Research Card + Allocation (禁止新数据)
输出: 7 模块结构化 Memo + Research Confidence

两套模板:
  Growth Memo: 变化 → 验证 → 兑现
  Recovery Memo: 优秀 → 错杀 → 修复
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pit.market import MarketData
from pit.financial import FinancialData
from growth_os.growth_probes import (
    probe_order_leadership, probe_capex_efficiency, probe_margin_resilience,
)


class InvestmentMemoEngine:
    """Memo 生成器 v1（纯规则，无 AI 文本生成）。"""

    def __init__(self, ind_map: dict = None):
        self._ind_map = ind_map or {}
        self._mkt = MarketData()
        self._fin = FinancialData()

    # ---------- 数据采集 (PIT) ----------
    def _probes(self, code: str, t_date: str) -> list[dict]:
        return [
            {"name": "订单领先", "probe": probe_order_leadership(code, t_date)},
            {"name": "CAPEX效率", "probe": probe_capex_efficiency(code, t_date)},
            {"name": "毛利韧性", "probe": probe_margin_resilience(code, t_date)},
        ]

    def _pe_info(self, code: str, t_date: str) -> dict:
        df = self._mkt.as_of(code, t_date)
        if "peTTM" not in df.columns or len(df) < 60:
            return {"current": None, "pct": None}
        pe = df["peTTM"].dropna()
        pe = pe[(pe > 0) & (pe < 500)]
        if len(pe) < 60:
            return {"current": None, "pct": None}
        cur = float(pe.iloc[-1])
        return {"current": round(cur, 1), "pct": round(float((pe < cur).mean()), 2)}

    # ---------- Memo 组装 ----------
    def generate(self, code: str, t_date: str, radar: str,
                 state: str, priority: str, drivers: str = "",
                 risks: str = "") -> dict:
        ind = self._ind_map.get(code, "未知")
        probes = self._probes(code, t_date)
        pe = self._pe_info(code, t_date)

        greens = [p for p in probes if p["probe"]["level"] == "green"]
        reds = [p for p in probes if p["probe"]["level"] == "red"]
        yellows = [p for p in probes if p["probe"]["level"] == "yellow"]

        # ---- 1. Identity ----
        identity = {
            "code": code, "industry": ind, "radar": radar,
            "state": state, "priority": priority,
        }

        # ---- 2. Why Now (按雷达) ----
        if radar == "recovery_radar":
            why_now = [
                "过去: 历史强势（曾被市场确认，RPS 曾 ≥70）",
                "现在: 价格/估值受压（回撤/PE 压缩）",
                f"验证: 基本面未破坏（green 探针 {len(greens)} 个，red {len(reds)} 个）",
                f"PE: 当前 {pe['current']}，历史分位 {pe['pct']}",
            ]
        else:
            why_now = [
                f"变化: {len(greens)} 个探针转绿（{'/'.join(g['name'] for g in greens) if greens else '待确认'}）",
                "市场状态: RPS 未确认（预期差窗口）",
                "逻辑: 经营变化可能领先于市场确认",
            ]

        # ---- 3. Thesis (Bull/Base/Bear) ----
        if radar == "recovery_radar":
            thesis = {
                "Bull": "周期/需求恢复 + 盈利释放 + 估值修复",
                "Base": "基本面维持，估值稳定（等待催化）",
                "Bear": "探针转红 / 行业下行 / 基本面确认恶化",
            }
        else:
            thesis = {
                "Bull": "订单/毛利改善持续 → 利润兑现 → 市场确认（46% 升级概率）",
                "Base": "变化延续但市场迟迟不确认（L1 持续）",
                "Bear": "变化证伪（订单回落 / 毛利转红）→ L0",
            }

        # ---- 4. Evidence ----
        evidence = {
            "green": [f"✓ {g['name']}: {g['probe']['label']}" for g in greens],
            "yellow": [f"△ {y['name']}: {y['probe']['label']}" for y in yellows],
            "red": [f"✗ {r['name']}: {r['probe']['label']}" for r in reds],
            "pe": pe,
        }

        # ---- 5. Catalyst (已知事件, 不预测) ----
        catalyst = {
            "next_report": "2026Q3 财报（10 月底披露）",
            "watch": ["收入增长是否兑现", "毛利/订单变化", "CAPEX 兑现节奏"],
        }

        # ---- 6. Thesis Broken ----
        broken = {
            "trigger_1": "订单/合同负债连续下降（探针转红）",
            "trigger_2": "毛利率连续 2 期下滑",
            "trigger_3": "行业范式恶化（周期顶部确认）",
            "trigger_4": "收入同比加速恶化",
        }

        # ---- 7. Research Action ----
        if radar == "recovery_radar":
            action = ["查看行业库存/需求周期位置", "确认下跌原因是估值还是基本面",
                      "跟踪 RPS 是否拐头（恢复信号）"]
        else:
            action = ["验证订单真实性（合同负债来源）", "确认利润兑现时间表",
                      "跟踪 RPS 确认进度（46% 升级概率）"]

        # ---- Research Confidence ----
        conf = 0.5
        conf += 0.15 * len(greens)  # 探针一致 +0.15/个 (上限 +0.45)
        conf -= 0.15 * len(reds)
        conf = float(np.clip(conf, 0.1, 0.95))

        return {
            "identity": identity,
            "why_now": why_now,
            "thesis": thesis,
            "evidence": evidence,
            "catalyst": catalyst,
            "thesis_broken": broken,
            "research_action": action,
            "confidence": round(conf, 2),
        }

    def render_markdown(self, memo: dict) -> str:
        """渲染为 Markdown（人工阅读用）。"""
        i = memo["identity"]
        lines = [
            f"# {i['code']} — Investment Memo",
            f"**行业**: {i['industry']} | **雷达**: {i['radar']} | "
            f"**状态**: {i['state']} | **优先级**: {i['priority']} | "
            f"**置信度**: {memo['confidence']:.0%}",
            "",
            "## Why Now",
        ] + [f"- {x}" for x in memo["why_now"]] + [
            "",
            "## Thesis",
            f"- Bull: {memo['thesis']['Bull']}",
            f"- Base: {memo['thesis']['Base']}",
            f"- Bear: {memo['thesis']['Bear']}",
            "",
            "## Evidence",
        ]
        ev = memo["evidence"]
        for g in ev["green"]:
            lines.append(f"- {g}")
        for y in ev["yellow"]:
            lines.append(f"- {y}")
        for r in ev["red"]:
            lines.append(f"- {r}")
        lines += [
            f"- PE: {ev['pe']['current']}（历史分位 {ev['pe']['pct']}）",
            "",
            "## Catalyst",
            f"- 下一节点: {memo['catalyst']['next_report']}",
            f"- 观察: {', '.join(memo['catalyst']['watch'])}",
            "",
            "## Thesis Broken（什么情况证明错）",
        ] + [f"- {v}" for v in memo["thesis_broken"].values()] + [
            "",
            "## Research Action",
        ] + [f"- {a}" for a in memo["research_action"]]
        return "\n".join(lines)
