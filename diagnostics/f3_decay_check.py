"""Audit C — F3 T+4Q 衰减来源判定 (C-Full 前置 #3)。

问题: T+4Q 所有 cell positive rate 收敛 ~50% (F0 0.49-0.55 / F1 ~0.52 / F2 ~0.51-0.53)。
R1 解释优先级: 指标均值回归(自然率~50%) > 基数效应(F1已处理) > 市场环境(第三)。

F3 检验设计:
1. 全市场基准: 每 t0 全部有 T+2Q/T+4Q outcome 公司的 positive rate / median yoy
   (无 F/M 条件) — 若恒定 ~0.5 → 均值回归主导 (自然率)
2. 若全市场基准随 t0 波动 (如 2023 vs 2025 不同) → 环境调制存在
3. F2M2 vs 全市场基准的**超额** (excess): T+2Q 超额大 → 状态有信息; T+4Q 超额→0 → 信息衰减完
4. 分 t0 看: F 梯度水平是否随环境移动 (水平由环境定, 排序由状态定)

方法: pilot panel 后处理 (已有 t2q_yoy/t4q_yoy)。纯离线。
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


def pos_med(s):
    v = pd.Series(s).dropna()
    if len(v) < 30:
        return None
    return round(float((v > 0).mean()), 3), round(float(v.median()), 2), len(v)


def main():
    panels = [pd.read_csv(f"diagnostics/growth_identity_pilot_{t0}.csv",
                          dtype={"code": str, "t0": str}) for t0 in T0S]
    df = pd.concat(panels, ignore_index=True)
    df["code"] = df["code"].astype(str).str.zfill(6)
    logger.info(f"panel {len(df)} 行")

    L = ["# Audit C — F3 T+4Q 衰减来源判定", "",
         f"**日期**: 2026-09-04 | **方法**: panel 后处理, 全市场基准对比", ""]

    # 1. 全市场基准 (分 t0 × horizon)
    L += ["## 1. 全市场基准 (无 F/M 条件) — 环境读数的代理", "",
          "| t0 | N | T+2Q pos | T+2Q med | T+4Q pos | T+4Q med |", "|---|---|---|---|---|---|"]
    bench = {}
    for t0 in T0S:
        sub = df[df["t0"] == t0]
        p2 = pos_med(sub["t2q_yoy"])
        p4 = pos_med(sub["t4q_yoy"])
        bench[t0] = {"p2": p2, "p4": p4}
        L.append(f"| {t0} | {len(sub)} | {p2[0] if p2 else '-'} | {p2[1] if p2 else '-'} "
                 f"| {p4[0] if p4 else '-'} | {p4[1] if p4 else '-'} |")

    # 2. F2M2 超额 vs 基准 (逐 t0)
    L += ["", "## 2. F2M2 超额 (excess over market) — 状态信息何时衰减", "",
          "| t0 | F2M2 T+2Q | 基准 T+2Q | 超额 | F2M2 T+4Q | 基准 T+4Q | 超额 |", "|---|---|---|---|---|---|---|"]
    for t0 in T0S:
        sub = df[df["t0"] == t0]
        f2m2 = sub[(sub["f"] == 2) & (sub["m"] == 2)]
        p2f = pos_med(f2m2["t2q_yoy"])
        p4f = pos_med(f2m2["t4q_yoy"])
        b2 = bench[t0]["p2"]
        b4 = bench[t0]["p4"]
        e2 = round(p2f[0] - b2[0], 3) if p2f and b2 else "-"
        e4 = round(p4f[0] - b4[0], 3) if p4f and b4 else "-"
        L.append(f"| {t0} | {p2f[0] if p2f else '-'} (n={p2f[2] if p2f else '-'}) | "
                 f"{b2[0] if b2 else '-'} | **{e2}** | "
                 f"{p4f[0] if p4f else '-'} (n={p4f[2] if p4f else '-'}) | "
                 f"{b4[0] if b4 else '-'} | **{e4}** |")

    # 3. 全 T+4Q 状态组 vs 基准 (合并4时点) — 信息衰减总览
    L += ["", "## 3. 状态信息半衰期 (合并 4 时点)", "",
          "| 组 | T+2Q pos | T+2Q 超额 | T+4Q pos | T+4Q 超额 |", "|---|---|---|---|---|"]
    allp2 = pos_med(df["t2q_yoy"])
    allp4 = pos_med(df["t4q_yoy"])
    L.append(f"| 全市场 | {allp2[0]} | — | {allp4[0]} | — |")
    for f in (0, 1, 2):
        for m in (0, 2):  # 对角与边缘
            sub = df[(df["f"] == f) & (df["m"] == m)]
            p2 = pos_med(sub["t2q_yoy"])
            p4 = pos_med(sub["t4q_yoy"])
            if not p2 or not p4:
                continue
            e2 = round(p2[0] - allp2[0], 3)
            e4 = round(p4[0] - allp4[0], 3)
            L.append(f"| F{f}M{m} | {p2[0]} (n={p2[2]}) | **{e2}** | {p4[0]} (n={p4[2]}) | **{e4}** |")

    # 4. 裁决行
    L += ["", "## 裁决规则 (R1: 均值回归 > 基数 > 环境)", "",
          "- 全市场 T+2Q/T+4Q pos 恒定 ~0.5 → 50% 是全市场自然率 → T+4Q 收敛 = 均值回归/信息衰减 (R1 第一顺位)",
          "- 全市场基准随 t0 波动显著 (如跨时点 >±8pp) → 环境调制存在 (水平移动)",
          "- F2M2 超额 T+2Q 大而 T+4Q ≈0 → 状态信息窗口约 2 季度, 非环境所致",
          "- 超额在 T+4Q 仍显著 (如 >+10pp) → 状态有 T+4Q 信息, 衰减不成立"]

    report = "\n".join(L)
    with open("diagnostics/growth_identity_f3_decay.md", "w") as f:
        f.write(report)
    print(report)
    logger.info("已输出 diagnostics/growth_identity_f3_decay.md")


if __name__ == "__main__":
    main()
