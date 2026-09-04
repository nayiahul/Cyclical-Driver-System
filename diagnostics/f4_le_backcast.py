"""Audit C — F4 L/E backcast 叠加 (C-Full 前置 #4, 最后前置)。

用当前 v3.5 规则 (state_machine + expectation_state) 对 4 个 pilot t0 的 panel code 回算 L/E 状态。
回答 Audit C 设计 §5 的 overlay 问题:
  1. 当前 L1×E0/E1 (Early Discovery cohort) 实际落在 3×3×B 哪些格子?
  2. L1×E0 的 T+2Q 兑现 vs F2M2 (Confirmed) 与全市场基准 — 左侧 vs 右侧的 Pilot 级对照

Model-version backcast 边界: 2026 v3.5 规则回放历史, ≠ 当年系统实际决策 (AUDIT_C v0.2 §1.5)。
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np
import pandas as pd
from loguru import logger

T0S = ["20230510", "20231110", "20240910", "20250512"]


def main():
    from industry import get_sw_industry
    from growth_os.lifecycle_research import prewarm_financial_cache
    from growth_os.state_machine import InvestmentStateModel
    from growth_os.expectation_state import ExpectationStateEngine
    from screener import compute_rps60

    ind_map = get_sw_industry()
    sm = InvestmentStateModel()
    eeng = ExpectationStateEngine()

    L = ["# Audit C — F4 L/E backcast 叠加结果", "",
         f"**日期**: 2026-09-04 | **方法**: v3.5 规则回放 4 pilot t0 (model-version backcast)",
         "**边界**: ≠ 当年系统实际决策; 仅回答 '当前规则面对当时数据会如何分类'", ""]

    all_dfs = []
    for t0 in T0S:
        df = pd.read_csv(f"diagnostics/growth_identity_pilot_{t0}.csv",
                         dtype={"code": str, "t0": str})
        df["code"] = df["code"].astype(str).str.zfill(6)
        codes = df["code"].tolist()

        logger.info(f"[{t0}] prewarm + RPS")
        prewarm_financial_cache(t0)
        rps_map = compute_rps60(codes, t0, ind_map)

        logger.info(f"[{t0}] L scan ({len(codes)} 只)")
        results = sm.scan(codes, t0, ind_map)
        l_map = {r.code: r.state for r in results}

        logger.info(f"[{t0}] E classify")
        e_map, e_vol = {}, {}
        for c in codes:
            r = eeng.classify(c, t0, rps=rps_map.get(c))
            e_map[c] = r.state
            e_vol[c] = r.vol_z

        df["L"] = df["code"].map(l_map)
        df["E"] = df["code"].map(e_map)
        df["E_volz"] = df["code"].map(e_vol)
        df["early"] = df.apply(lambda r: r["L"] in ("L1", "L2") and r["E"] in ("E0", "E1"), axis=1)
        all_dfs.append(df)
        logger.info(f"[{t0}] L 分布 {df['L'].value_counts().to_dict()} | "
                    f"E 分布 {df['E'].value_counts().to_dict()} | early {df['early'].sum()}")

    df = pd.concat(all_dfs, ignore_index=True)
    df.to_csv("diagnostics/growth_identity_panel_le.csv", index=False)
    logger.info(f"panel+L/E: {len(df)} 行; early (L1/2×E0/1): {df['early'].sum()}")

    def stat(sub, col="t2q_yoy"):
        v = sub[col].dropna()
        if len(v) < 30:
            return f"n={len(sub)}⚠"
        bench = v.mean()  # 组内基准不可 — 组间用全市场
        return round(float((v > 0).mean()), 3), round(float(v.median()), 2), len(v)

    # 全市场基准 (T+2Q)
    allv = df["t2q_yoy"].dropna()
    mkt_pos = round(float((allv > 0).mean()), 3)
    L += [f"**全市场基准 T+2Q pos**: {mkt_pos} (n={len(allv)})", ""]

    # 1. L1×E0/E1 落在 3×3×B 哪些格子
    L += ["## 1. Early cohort (L1/L2 × E0/E1) 在 3×3×B 的分布", "",
          "| cell | Early n | Early/全cell | T+2Q pos (Early) |", "|---|---|---|---|"]
    for fm in ["F0M0", "F1M0", "F1M1", "F2M0", "F2M1", "F2M2"]:
        f, m = int(fm[1]), int(fm[3])
        cell = df[(df["f"] == f) & (df["m"] == m)]
        if not len(cell):
            continue
        early = cell[cell["early"]]
        if not len(early):
            L.append(f"| {fm} | 0 | 0% | - |")
            continue
        st = stat(early)
        L.append(f"| {fm} | {len(early)} | {round(len(early)/len(cell)*100)}% | "
                 f"{st[0] if isinstance(st, tuple) else st} (n={st[2] if isinstance(st, tuple) else ''}) |")

    # 2. 核心对照: Early 各组 vs F2M2 (Confirmed) vs 全市场 (T+2Q)
    L += ["", "## 2. Pilot 级对照: Early vs Confirmed vs 市场 (T+2Q)", "",
          "| cohort | 定义 | N | T+2Q pos | 超额 |", "|---|---|---|---|---|"]
    cohorts = {
        "F2M2 Confirmed": (df["f"] == 2) & (df["m"] == 2),
        "F2M0 基本面强未确认": (df["f"] == 2) & (df["m"] == 0),
        "Early(L1/2×E0/1) 全": df["early"],
        "Early×F2": df["early"] & (df["f"] == 2),
        "Early×F2M0": df["early"] & (df["f"] == 2) & (df["m"] == 0),
        "Early×F1": df["early"] & (df["f"] == 1),
        "F0M0 噪声区": (df["f"] == 0) & (df["m"] == 0),
    }
    for name, mask in cohorts.items():
        sub = df[mask]
        v = sub["t2q_yoy"].dropna()
        if len(v) < 30:
            L.append(f"| {name} | n={len(sub)}⚠ | - | - |")
            continue
        pos = round(float((v > 0).mean()), 3)
        ex = round(pos - mkt_pos, 3)
        L.append(f"| {name} | n={len(sub)} | {pos} | **{ex}** |")

    # 3. E/L 分解: L1 的 E 分档兑现 (左侧问题核心)
    L += ["", "## 3. L1 cohort 按 E 分档 (左侧发现的时间差价值)", "",
          "| L1 子组 | N | T+2Q pos | 超额 |", "|---|---|---|---|"]
    for e in ("E0", "E1", "E2", "E3"):
        sub = df[(df["L"] == "L1") & (df["E"] == e)]
        if not len(sub):
            continue
        v = sub["t2q_yoy"].dropna()
        if len(v) < 30:
            L.append(f"| L1×{e} | {len(sub)}⚠ | - | - |")
            continue
        pos = round(float((v > 0).mean()), 3)
        L.append(f"| L1×{e} | {len(sub)} | {pos} | **{round(pos-mkt_pos,3)}** |")

    report = "\n".join(L)
    with open("diagnostics/growth_identity_f4_le_backcast.md", "w") as f:
        f.write(report)
    print(report)
    logger.info("已输出 diagnostics/growth_identity_f4_le_backcast.md")


if __name__ == "__main__":
    main()
