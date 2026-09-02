"""Step 7-C': 历史回填演练 — 让 Ledger 快速获得"童年经验"。

原理:
  用历史采样日 (2025-05-06 / 2025-09-01) 模拟"当时的 Research Memo"
  (状态/雷达/证据 全部只用该时点之前数据 — PIT 天然隔离)
  → 回填到 2026-08-31 的真实结果 (价格/状态迁移/探针变化)
  → ThesisReview + 复盘统计

验证:
  1. Ledger 回填机制正确性 (真实数据)
  2. 第一批 Evidence 统计 (什么证据有效)
  3. 失败原因可分类

注意:
  - 不是回测收益 (系统不是选股模型)
  - 验证的是"研究判断链是否成立"
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import numpy as np
import pandas as pd
from collections import Counter

from growth_os.ledger import OutcomeLedger
from growth_os.state_machine import InvestmentStateModel
from growth_os.lifecycle_research import prewarm_financial_cache
from growth_os.growth_probes import (
    probe_order_leadership, probe_capex_efficiency, probe_margin_resilience,
)
from pit.market import MarketData
from industry import get_sw_industry

CHECK_DATE = "20260831"  # 回填终点 (当前最新数据日)

HISTORICAL_DATES = ["20250506", "20250901"]  # 模拟研究日 (已有采样数据, PIT 保证)


def build_snapshot(day: int, aud: pd.DataFrame, hist_max: dict):
    """从采样数据重建该日的候选池快照 (PIT: 只用 day 及之前信息)。"""
    sub = aud[aud["day"] == day].copy()
    sub["code"] = sub["code"].astype(str).str.zfill(6)

    # 重建状态 (与 state_machine 同阈值)
    sub["disc_q"] = np.where(sub["discovery"] >= 0.5, "high", "low")
    def st(rps, disc):
        if disc == "high":
            if rps >= 70: return "L3"
            if rps >= 40: return "L2"
            return "L1"
        return "L0"
    sub["state"] = [st(r, d) for r, d in zip(sub["rps"], sub["disc_q"])]

    # L5 判定 (简化: 用 hist_rps + 探针 + 回撤近似)
    ind = get_sw_industry()
    from growth_os.l5_recovery import L5RecoveryEngine, PARADIGM_MAP  # noqa
    l5e = L5RecoveryEngine(ind_map=ind)
    rps_map = dict(zip(sub["code"], sub["rps"]))
    l5_results = {r.code: r for r in l5e.scan(sub["code"].tolist(), str(day), rps_map=rps_map, hist_rps_map=hist_max)}
    sub["state"] = [l5_results.get(c).state if l5_results.get(c) and l5_results.get(c).state.startswith("L5") else s
                    for c, s in zip(sub["code"], sub["state"])]

    # 雷达
    sub["radar"] = np.where(sub["state"].str.startswith("L5"), "recovery_radar",
                   np.where(sub["state"].isin(["L1", "L2"]), "growth_radar", "watch"))
    sub["n_green"] = (sub[["order", "capex", "margin"]] >= 0.5).sum(axis=1)
    sub["n_red"] = (sub[["order", "capex", "margin"]] == 0).sum(axis=1)
    return sub


def main():
    aud = pd.read_csv("baseline/discovery_audit_2022_2025.csv")
    aud["code"] = aud["code"].astype(str).str.zfill(6)
    aud["day"] = aud["day"].astype(int)
    ind = get_sw_industry()
    sm = InvestmentStateModel(ind_map=ind)
    mkt = MarketData()
    ledger = OutcomeLedger(ledger_dir="data/ledger_historical")
    os.makedirs("data/ledger_historical", exist_ok=True)

    # 清空演练目录 (可重复运行)
    for f in ["outcomes.jsonl", "reviews.jsonl"]:
        p = f"data/ledger_historical/{f}"
        if os.path.exists(p):
            os.remove(p)

    all_reviews = []
    for day_str in HISTORICAL_DATES:
        day = int(day_str)
        # 历史 RPS 峰值 (day 之前所有采样日 — PIT)
        prior = aud[(aud["day"] < day) & (aud["code"].isin(aud[aud["day"] == day]["code"]))]
        hist_max = prior.groupby("code")["rps"].max().to_dict()

        snap = build_snapshot(day, aud, hist_max)
        # 双雷达 Top25+25 (RA 近似: green 密度 + 未确认)
        g = snap[snap["radar"] == "growth_radar"].copy()
        r = snap[snap["radar"] == "recovery_radar"].copy()
        g["ra"] = 0.5 * g["n_green"] / 3 + 0.5 * (1 - g["rps"] / 100)
        r["ra"] = 0.5 * r["n_green"] / 3 + 0.5 * (1 - r["rps"] / 100)
        top = pd.concat([g.sort_values("ra", ascending=False).head(25),
                         r.sort_values("ra", ascending=False).head(25)])
        print(f"\n=== 模拟研究日 {day_str} ===  Top50 (Growth {sum(top['radar']=='growth_radar')} + Recovery {sum(top['radar']=='recovery_radar')})")

        # 生成 "Memo" 记录 (T0)
        for _, row in top.iterrows():
            oid = f"RO-{day_str}-{row['code']}"
            greens = [p for p in ["order", "capex", "margin"] if row[p] >= 0.5]
            ledger._append("outcomes.jsonl", {
                "outcome_id": oid, "stock": row["code"], "memo_date": day_str,
                "radar": row["radar"], "state_at_memo": row["state"],
                "confidence": 0.5 + 0.15 * len(greens),
                "created_at": "HISTORICAL_BACKFILL",
                "price_outcome": {"t90": None, "max_drawdown_90": None},
                "state_transition": {"actual_path": None, "t90_state": None},
                "thesis_outcome": {"verdict": "pending"},
                "evidence_effectiveness": {"green_probes_at_memo": greens,
                                           "which_probes_held": None,
                                           "which_probes_failed": None},
            })

        # 回填 (2026-08-31: 价格 + 状态 + 探针)
        prewarm_financial_cache(CHECK_DATE)
        for _, row in top.iterrows():
            oid = f"RO-{day_str}-{row['code']}"
            rec = ledger.backfill(oid, CHECK_DATE, sm=sm)
            if rec:
                review = ledger.generate_review(oid, CHECK_DATE, sm=sm)
                if review:
                    all_reviews.append(review)

    # ============ 复盘统计 ============
    print("\n" + "=" * 60)
    print("历史回填演练结果")
    print("=" * 60)
    revs = pd.DataFrame(all_reviews)
    if len(revs) == 0:
        print("无复盘结果")
        return
    print(f"复盘样本: {len(revs)} 条 (2025-05 + 2025-09 两期 Top50)")

    print(f"\nThesis 判定分布: {dict(revs['thesis_verdict'].value_counts())}")
    print(f"价格判定: {dict(revs['price_verdict'].value_counts())}")
    print(f"状态判定: {dict(revs['state_verdict'].value_counts())}")

    # 证据保持率
    held = []
    for r in all_reviews:
        led = r["attribution"].get("evidence_led") or []
        held.extend(led)
    print(f"\n探针保持统计 (复盘时仍 green): {dict(Counter(held))}")

    # 按雷达拆分
    recs = ledger._load("outcomes.jsonl")
    rec_df = pd.DataFrame(recs)
    merged = revs.merge(rec_df[["outcome_id", "radar", "state_at_memo"]], on="outcome_id", how="left")
    for radar in ["growth_radar", "recovery_radar"]:
        sub = merged[merged["radar"] == radar]
        if len(sub):
            print(f"\n{radar}: n={len(sub)} | confirmed/partial: {(sub['thesis_verdict'].isin(['confirmed','partial'])).mean():.0%}"
                  f" | 价格正: {(sub['price_verdict']=='positive').mean():.0%}"
                  f" | 状态恢复: {(sub['state_verdict']=='recovered').mean():.0%}")

    print(f"\n数据已保存: data/ledger_historical/ (outcomes + reviews)")


if __name__ == "__main__":
    main()
