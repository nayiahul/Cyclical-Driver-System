"""Audit C — F2 B_WEAK 子类拆分 (C-Full 前置 #2)。

问题 (F1 残余): 排除低基数后 F2 组仍残留 1-3pp 反直觉 (T+4Q OK<WEAK)。
F2 裁决: 把 B_WEAK 拆成两个经济状态不同的子类:
  - WEAK_ROIC:   margin 非 red 但 ROIC<=0 (周期底部/反转早期, 利润弹性大)
  - WEAK_MARGIN: margin red (经营质量恶化: 竞争/成本侵蚀)
假设: 残余反直觉若来自 WEAK_ROIC (弹性) → 可解释; 若 WEAK_MARGIN 也 >OK → B_proxy 需重审。

方法: 对 pilot panel 每 code×t0 重算 margin_state (growth_probes 口径) + ROIC 最新值,
在 panel CSV 上后处理拆分。纯离线。
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np
import pandas as pd
from loguru import logger

from data_governance import filter_available_reports

T0S = ["20230510", "20231110", "20240910", "20250512"]


def margin_state(gm_series: pd.Series, rev_yoy_latest: float) -> str:
    s = gm_series.dropna().tail(12)
    if len(s) < 8:
        return "unknown"
    gm_recent = s.iloc[-4:].mean()
    gm_old = s.iloc[-8:-4].mean()
    gm_trend = gm_recent - gm_old
    gm_std = s.std()
    if gm_recent > 35 and gm_trend > 0 and (rev_yoy_latest or 0) > 20:
        return "green"
    if gm_recent > 30 and abs(gm_trend) < 2:
        return "green"
    if gm_trend < -3 or gm_std > 8:
        return "red"
    return "yellow"


def main():
    raw = pd.read_csv("data/cache/tdx_financials.csv",
                      dtype={"code": str, "report_date_str": str})
    raw["code"] = raw["code"].astype(str).str.zfill(6)

    panels = []
    for t0 in T0S:
        df = pd.read_csv(f"diagnostics/growth_identity_pilot_{t0}.csv",
                         dtype={"code": str, "t0": str})
        df["code"] = df["code"].astype(str).str.zfill(6)
        # 重算 margin state + ROIC (as-of t0, PIT)
        avail = filter_available_reports(raw, t0)
        avail = avail.sort_values("report_date_str")
        g = avail.groupby("code")
        marg, roic_last = {}, {}
        for code, sub in g:
            gm = sub["gross_margin"].dropna()
            rev = sub["revenue_yoy"].dropna()
            rev_latest = float(rev.iloc[-1]) if len(rev) else None
            marg[code] = margin_state(gm, rev_latest)
            r = sub["roic"].dropna()
            roic_last[code] = float(r.iloc[-1]) if len(r) else None
        df["m_state"] = df["code"].map(marg).fillna("unknown")
        df["roic_latest"] = df["code"].map(roic_last)
        # 拆分 b_v35 → 5 类
        def split_b(row):
            b = row["b_v35"]
            if b in ("OK", "YELLOW", "UNKNOWN"):
                return b
            # WEAK: red 或 ROIC<=0
            if row["m_state"] == "red":
                return "WEAK_MARGIN"   # 经营质量恶化
            return "WEAK_ROIC"          # margin 非 red 但 ROIC<=0 (周期底部/反转)
        df["b5"] = df.apply(split_b, axis=1)
        panels.append(df)

    df = pd.concat(panels, ignore_index=True)
    logger.info(f"panel 合并 {len(df)} 行; b5 分布: {df['b5'].value_counts().to_dict()}")

    # 低基数排除 (F1 门槛 5000万, 复用 ttm_base — 从 F1 结果文件没有, 重算简单版:
    # 直接从 pilot panel 无 ttm → 用 roic>0 公司 ttm 近似? 不 — 读 f1 csv 结果会缺列。
    # 简化: 此脚本聚焦拆分, 用 T+4Q 全样本 + 报告含/不含 roic<=0 已天然分层。
    # 排除低基数需 ttm — 从 TDX 重算 (与 F1 相同逻辑)
    ttm_map = {}
    raw2 = raw.sort_values("report_date_str")
    for code, g in raw2.groupby("code"):
        g = g.dropna(subset=["deducted_profit_q"]).tail(16)
        q, dates = g["deducted_profit_q"].tolist(), g["report_date_str"].tolist()
        ttm = {}
        for i in range(len(dates)):
            win = q[max(0, i - 3): i + 1]
            if len(win) == 4:
                ttm[dates[i]] = sum(win)
        ttm_map[code] = ttm

    def ttm_at(code, t0):
        t = ttm_map.get(code)
        if not t:
            return None
        cand = {d: v for d, v in t.items() if d <= t0}
        return cand[max(cand)] if cand else None

    df["ttm_base"] = [ttm_at(c, t) for c, t in zip(df["code"], df["t0"])]
    df["low_base"] = df["ttm_base"] < 5e7

    L = ["# Audit C — F2 B_WEAK 子类拆分结果", "",
         f"**日期**: 2026-09-04 | **方法**: panel 后处理, WEAK → WEAK_MARGIN(margin red) / WEAK_ROIC(ROIC<=0)",
         "", f"**b5 分布**: {df['b5'].value_counts().to_dict()}", ""]

    def stat(sub, col="t4q_yoy"):
        v = sub[col].dropna()
        if len(v) < 30:
            return f"n={len(sub)}⚠"
        return f"pos={round(float((v > 0).mean()), 3)} med={round(float(v.median()), 2)} n={len(v)}"

    # 核心表: F2 组 (F1 残余反直觉所在), 含低基数 vs 排除
    L += ["## F2 组 B5 子类 × T+4Q (含低基数)", "", "| cell | OK | YELLOW | WEAK_ROIC | WEAK_MARGIN | WEAK(合并, 参考) |", "|---|---|---|---|---|---|"]
    for fm in ["F2M0", "F2M1", "F2M2"]:
        f, m = int(fm[1]), int(fm[3])
        sub = df[(df["f"] == f) & (df["m"] == m)]
        row = [fm]
        for b in ["OK", "YELLOW", "WEAK_ROIC", "WEAK_MARGIN"]:
            row.append(stat(sub[sub["b5"] == b]))
        row.append(stat(sub[sub["b_v35"] == "WEAK"]))
        L.append("| " + " | ".join(row) + " |")

    L += ["", "## F2 组 B5 × T+4Q (排除低基数, ttm>=5000万)", "", "| cell | OK | YELLOW | WEAK_ROIC | WEAK_MARGIN |", "|---|---|---|---|---|"]
    for fm in ["F2M0", "F2M1", "F2M2"]:
        f, m = int(fm[1]), int(fm[3])
        sub = df[(df["f"] == f) & (df["m"] == m) & (~df["low_base"])]
        row = [fm]
        for b in ["OK", "YELLOW", "WEAK_ROIC", "WEAK_MARGIN"]:
            row.append(stat(sub[sub["b5"] == b]))
        L.append("| " + " | ".join(row) + " |")

    # 裁决行
    L += ["", "## 裁决 (残余反直觉归因)", ""]
    for fm in ["F2M0", "F2M1", "F2M2"]:
        f, m = int(fm[1]), int(fm[3])
        sub = df[(df["f"] == f) & (df["m"] == m) & (~df["low_base"])]
        ok = stat(sub[sub["b5"] == "OK"], "t4q_yoy")
        wr = stat(sub[sub["b5"] == "WEAK_ROIC"], "t4q_yoy")
        wm = stat(sub[sub["b5"] == "WEAK_MARGIN"], "t4q_yoy")
        L.append(f"- {fm}: OK {ok} | WEAK_ROIC {wr} | WEAK_MARGIN {wm}")
    L += ["", "解读规则:",
          "- WEAK_ROIC > OK 且 WEAK_MARGIN <= OK → 残余反直觉来自周期底部弹性, B_proxy(质量)逻辑不受损",
          "- WEAK_MARGIN 也 > OK → 质量代理反直觉真实, B_v35 定义需重审",
          "- 样本 <30 (⚠) 不裁决"]

    report = "\n".join(L)
    with open("diagnostics/growth_identity_f2_weak_split.md", "w") as f:
        f.write(report)
    print(report)
    logger.info("已输出 diagnostics/growth_identity_f2_weak_split.md")


if __name__ == "__main__":
    main()
