"""Research Outcome Ledger v1 — 结果账本 (Step 7-B)。

数据契约: docs/OUTCOME_LEDGER_SCHEMA.md
存储: data/ledger/outcomes.jsonl + decisions.jsonl + reviews.jsonl

功能:
  init_from_book: 从 Daily Research Book 生成 T0 记录
  backfill:      T+30/90/180/365 回填价格/状态/探针
  generate_review: T+90 ThesisReview (归因 + 校准建议)
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from pit.market import MarketData
from growth_os.state_machine import InvestmentStateModel
from growth_os.growth_probes import (
    probe_order_leadership, probe_capex_efficiency, probe_margin_resilience,
)

LEDGER_DIR = "data/ledger"


class OutcomeLedger:
    """结果账本 v1。"""

    def __init__(self, ledger_dir: str = LEDGER_DIR):
        self.dir = ledger_dir
        os.makedirs(ledger_dir, exist_ok=True)
        self._mkt = MarketData()

    # ---------- 存储 ----------
    def _append(self, fname: str, record: dict):
        with open(os.path.join(self.dir, fname), "a") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _load(self, fname: str) -> list[dict]:
        path = os.path.join(self.dir, fname)
        if not os.path.exists(path):
            return []
        return [json.loads(line) for line in open(path) if line.strip()]

    # ---------- T0: 从 Research Book 初始化 ----------
    def init_from_book(self, book_csv: str, t_date: str) -> int:
        df = pd.read_csv(book_csv)
        df["code"] = df["code"].astype(str).str.zfill(6)
        n = 0
        for _, row in df.iterrows():
            oid = f"RO-{t_date}-{row['code']}"
            existing = {r["outcome_id"] for r in self._load("outcomes.jsonl")}
            if oid in existing:
                continue
            rec = {
                "outcome_id": oid,
                "stock": row["code"],
                "memo_date": t_date,
                "radar": row["radar"],
                "state_at_memo": row["lifecycle_state"],
                "confidence": float(row.get("confidence", np.nan)),
                "ra_score": float(row.get("ra_score", np.nan)),
                "created_at": datetime.now().isoformat(),
                "price_outcome": {"t30": None, "t90": None, "t180": None,
                                  "t365": None, "max_drawdown_90": None,
                                  "vs_industry_90": None},
                "state_transition": {"actual_path": None, "t90_state": None,
                                     "t180_state": None},
                "thesis_outcome": {"revenue_confirmed": None,
                                   "margin_confirmed": None,
                                   "order_confirmed": None,
                                   "verdict": "pending"},
                "evidence_effectiveness": {
                    "green_probes_at_memo": [
                        p["name"] for p in self._probes_at(row["code"], t_date)
                        if p["probe"]["level"] == "green"],
                    "which_probes_held": None, "which_probes_failed": None},
            }
            self._append("outcomes.jsonl", rec)
            n += 1
        return n

    def _probes_at(self, code: str, t_date: str) -> list[dict]:
        return [
            {"name": "order", "probe": probe_order_leadership(code, t_date)},
            {"name": "capex", "probe": probe_capex_efficiency(code, t_date)},
            {"name": "margin", "probe": probe_margin_resilience(code, t_date)},
        ]

    # ---------- 回填 (T+90 示例) ----------
    def backfill(self, outcome_id: str, check_date: str,
                 sm: InvestmentStateModel = None) -> Optional[dict]:
        """回填价格与状态。返回更新后的记录。"""
        recs = self._load("outcomes.jsonl")
        for i, rec in enumerate(recs):
            if rec["outcome_id"] != outcome_id:
                continue
            code = rec["stock"]
            # 价格结果 (相对 memo_date)
            memo_date = rec["memo_date"]
            ret = self._fwd_return(code, memo_date, check_date)
            if ret is not None:
                rec["price_outcome"]["t90"] = round(ret, 4)
            # 状态重算
            if sm is not None:
                new_state = sm.evaluate(code, check_date)
                rec["state_transition"]["t90_state"] = new_state.state
                rec["state_transition"]["actual_path"] = (
                    f"{rec['state_at_memo']}→{new_state.state}")
            # 探针复核
            probes = self._probes_at(code, check_date)
            held = [p["name"] for p in probes if p["probe"]["level"] == "green"]
            rec["evidence_effectiveness"]["which_probes_held"] = held
            rec["evidence_effectiveness"]["which_probes_failed"] = [
                p["name"] for p in probes if p["probe"]["level"] == "red"]
            recs[i] = rec
            return rec
        return None

    def _fwd_return(self, code: str, start: str, end: str) -> Optional[float]:
        try:
            p1 = self._mkt.close_on_or_before(code, start)
            p2 = self._mkt.close_on_or_before(code, end)
            if p1 and p2 and p1 > 0:
                return p2 / p1 - 1
        except Exception:
            pass
        return None

    # ---------- Thesis Review (T+90) ----------
    def generate_review(self, outcome_id: str, check_date: str,
                        sm: InvestmentStateModel = None) -> Optional[dict]:
        rec = self.backfill(outcome_id, check_date, sm)
        if rec is None:
            return None
        ret = rec["price_outcome"].get("t90")
        state = rec["state_transition"].get("t90_state")
        # 判定
        price_verdict = "positive" if (ret or 0) > 0 else "negative"
        recovered = state in ("L2", "L3") if state else False
        state_verdict = "recovered" if recovered else "not_recovered"
        held_n = len(rec["evidence_effectiveness"].get("which_probes_held") or [])
        thesis_verdict = ("confirmed" if price_verdict == "positive" and recovered
                          else "partial" if price_verdict == "positive" or recovered
                          else "failed")
        review = {
            "review_id": f"TR-{check_date}-{rec['stock']}",
            "outcome_id": outcome_id,
            "generated_at": datetime.now().isoformat(),
            "price_verdict": price_verdict,
            "state_verdict": state_verdict,
            "thesis_verdict": thesis_verdict,
            "attribution": {
                "pe_repaired": None, "industry_improved": None,
                "fundamentals_held": held_n > 0,
                "evidence_led": rec["evidence_effectiveness"].get("which_probes_held"),
            },
            "learning": {
                "confidence_was": rec.get("confidence"),
                "probe_adjustment": None,
            },
        }
        self._append("reviews.jsonl", review)
        return review

    # ---------- 聚合: 证据有效性 ----------
    def evidence_summary(self) -> dict:
        recs = self._load("outcomes.jsonl")
        reviews = self._load("reviews.jsonl")
        if not recs or not reviews:
            return {"n": 0}
        held_stats = {}
        for r in reviews:
            led = r["attribution"].get("evidence_led") or []
            for probe in led:
                held_stats[probe] = held_stats.get(probe, 0) + 1
        return {
            "n_outcomes": len(recs),
            "n_reviews": len(reviews),
            "probe_hold_count": held_stats,
        }
