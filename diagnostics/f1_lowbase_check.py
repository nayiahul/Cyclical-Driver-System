"""Audit C — F1 低基数口径修正 (C-Full 前置 #1)。

问题 (Pilot 发现): deducted_profit_yoy > 0 含低基数扭亏公司 (ROIC<=0 但利润转正),
yoy 天然虚高 → B_v35 分层反直觉 (F2 组 T+4Q OK<WEAK) 疑似基数伪影。

F1 修正: 对每个 company×t0, 计算 t0 时 TTM 扣非利润 (最近4单季和);
标记 low_base = TTM < 门槛 (主: 5000万; 敏感性: 1亿/3000万)。
对比 含低基数 vs 排除低基数 的 Table1/Table2 — 若反直觉方向在排除后消失/减弱 → 伪影证实。

方法: 在 pilot panel CSV 上后处理 (不需重跑主审计)。纯离线诊断。
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
THRESHOLDS = [3e7, 5e7, 1e8]  # 3000万 / 5000万 / 1亿 (元)


def load_ttm_map() -> dict:
    """code × report_date_str(<=各t0) → 最近4单季扣非和 (TTM)。"""
    raw = pd.read_csv("data/cache/tdx_financials.csv",
                      dtype={"code": str, "report_date_str": str},
                      usecols=["code", "report_date_str", "deducted_profit_q"])
    raw["code"] = raw["code"].astype(str).str.zfill(6)
    raw = raw.sort_values("report_date_str")
    # 每 code: 报告期序列 → TTM (rolling 4 sum of 单季)
    out = {}
    for code, g in raw.groupby("code"):
        g = g.dropna(subset=["deducted_profit_q"]).tail(16)
        q = g["deducted_profit_q"].tolist()
        dates = g["report_date_str"].tolist()
        # TTM 需要在报告期上滚动 — 单季累4期即 TTM (近似, 忽略累计/单季口径差异)
        ttm = {}
        for i in range(len(dates)):
            win = q[max(0, i - 3): i + 1]
            if len(win) == 4:
                ttm[dates[i]] = sum(win)
        out[code] = ttm
    return out


def ttm_at(ttm_map: dict, code: str, t0: str) -> float | None:
    ttm = ttm_map.get(code)
    if not ttm:
        return None
    # t0 前最近的报告期 TTM
    cand = {d: v for d, v in ttm.items() if d <= t0}
    if not cand:
        return None
    latest = max(cand)
    return cand[latest]


def main():
    ttm_map = load_ttm_map()
    logger.info(f"TTM 表构建完成: {len(ttm_map)} 只")

    panels = [pd.read_csv(f"diagnostics/growth_identity_pilot_{t0}.csv",
                          dtype={"code": str, "t0": str}) for t0 in T0S]
    df = pd.concat(panels, ignore_index=True)
    df["code"] = df["code"].astype(str).str.zfill(6)
    logger.info(f"panel 合并: {len(df)} 行")

    df["ttm_base"] = [ttm_at(ttm_map, c, t) for c, t in zip(df["code"], df["t0"])]
    logger.info(f"TTM 可得率: {df['ttm_base'].notna().mean():.3f}")

    def stat(sub, col):
        vals = sub[col].dropna()
        n = len(vals)
        if not n:
            return None
        return {"n": n, "pos": round(float((vals > 0).mean()), 3),
                "med": round(float(vals.median()), 2)}

    out_lines = ["# Audit C — F1 低基数口径修正结果", "",
                 f"**日期**: 2026-09-04 | **方法**: pilot panel 后处理 (TTM 门槛标记), 未重跑主审计",
                 f"**TTM 可得率**: {df['ttm_base'].notna().mean():.3f}", ""]

    for thr in THRESHOLDS:
        out_lines += [f"\n## 门槛 {thr/1e8:.1f}亿 — 排除低基数前后对比 (T+4Q, F2 组 B 分层)",
                      "", "| B_v35 | 含低基数 pos | 排除后 pos | 排除后 n | 低基数 n | 反直觉? |",
                      "|---|---|---|---|---|---|"]
        for fm in ["F2M0", "F2M1", "F2M2"]:
            f, m = int(fm[1]), int(fm[3])
            sub = df[(df["f"] == f) & (df["m"] == m)]
            for b in ("OK", "WEAK", "YELLOW"):
                sb = sub[sub["b_v35"] == b]
                full = stat(sb, "t4q_yoy")
                lowbase = sb[sb["ttm_base"] < thr]
                ex = sb[sb["ttm_base"] >= thr]
                st_ex = stat(ex, "t4q_yoy")
                if not full or not st_ex:
                    continue
                # 反直觉判定: WEAK pos > OK pos (排除前)
                out_lines.append(
                    f"| {fm}/{b} | {full['pos']} (n={full['n']}) | {st_ex['pos']} "
                    f"(n={st_ex['n']}) | {st_ex['n']} | {len(lowbase)} | |")
        # 直接对比 OK vs WEAK 反直觉是否消除
        out_lines += ["", "**OK vs WEAK 反直觉检验 (排除低基数后)**:", ""]
        for fm in ["F2M0", "F2M1", "F2M2"]:
            f, m = int(fm[1]), int(fm[3])
            sub = df[(df["f"] == f) & (df["m"] == m) & (df["ttm_base"] >= thr)]
            ok = stat(sub[sub["b_v35"] == "OK"], "t4q_yoy")
            wk = stat(sub[sub["b_v35"] == "WEAK"], "t4q_yoy")
            if ok and wk:
                verdict = "OK>WEAK (反直觉消失)" if ok["pos"] >= wk["pos"] else "仍 OK<WEAK (反直觉残留)"
                out_lines.append(f"- {fm}: OK {ok['pos']} vs WEAK {wk['pos']} → {verdict}")

    # T+2Q 也出一版 (主兑现窗口)
    out_lines += ["", "## T+2Q F 梯度 (排除低基数 vs 含, 门槛 5000万)", "",
                  "| 组 | F0 pos | F1 pos | F2 pos |", "|---|---|---|---|"]
    sub = df[df["ttm_base"] >= 5e7]
    row = []
    for f in (0, 1, 2):
        s = stat(sub[sub["f"] == f], "t2q_yoy")
        row.append(f"{s['pos']} (n={s['n']})" if s else "-")
    out_lines.append(f"| 排除低基数 | " + " | ".join(row) + " |")

    report = "\n".join(out_lines)
    with open("diagnostics/growth_identity_f1_lowbase.md", "w") as f:
        f.write(report)
    print(report[:2500])
    logger.info("已输出 diagnostics/growth_identity_f1_lowbase.md")


if __name__ == "__main__":
    main()
