"""Step 6-B-4: Daily Research Book — Radar-Quota Top50 + Investment Memo。

流程:
  research_pool_20260901.csv (2868 只, 已含 lifecycle 标签)
    → 双雷达 RA 排序 (Growth 25 + Recovery 25)
    → 每只生成 Memo (含 Evidence Trace)
    → 输出 Daily Research Book (md + csv)

输出:
  output/research_book_20260901.md   人工阅读
  output/research_book_20260901.csv  机器/复盘
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from loguru import logger

from growth_os.memo_engine import InvestmentMemoEngine
from growth_os.lifecycle_research import prewarm_financial_cache
from industry import get_sw_industry

T_DATE = "20260831"
POOL = "output/research_pool_v3_20260901.csv"  # v3: 含 expectation_state
OUT = "output/research_book_20260901"

def main():
    df = pd.read_csv(POOL)
    df["code"] = df["code"].astype(str).str.zfill(6)
    logger.info(f"研究池: {len(df)} 只 (v3: L/E 双轴)")

    prewarm_financial_cache(T_DATE)
    ind = get_sw_industry()
    eng = InvestmentMemoEngine(ind_map=ind)

    # 双雷达池
    growth_pool = df[df["radar"] == "growth_radar"]
    recovery_pool = df[df["radar"] == "recovery_radar"]
    logger.info(f"Growth 池 {len(growth_pool)} | Recovery 池 {len(recovery_pool)}")

    # 逐只计算 RA 分数 + Memo
    rows = []
    for _, row in df[df["research_priority"] == "A"].iterrows():
        code = row["code"]
        probes = eng._probes(code, T_DATE)
        n_green = sum(1 for p in probes if p["probe"]["level"] == "green")
        n_red = sum(1 for p in probes if p["probe"]["level"] == "red")
        pe = eng._pe_info(code, T_DATE)
        pe_pct = pe["pct"] if pe["pct"] is not None else 0.5

        # Growth RA: 证据 30% + 未确认 30% + L1 权重 20% + 可执行 20%
        # Recovery RA: 证据 30% + 非red 30% + 未确认 20% + 风险 20%
        if row["radar"] == "growth_radar":
            ra = (0.3 * min(n_green, 3) / 3
                  + 0.3 * (1 - pe_pct)
                  + 0.2 * (1.0 if row["lifecycle_state"] == "L1" else 0.6)
                  + 0.2 * (1 - n_red / 3))
        else:
            ra = (0.3 * min(n_green, 3) / 3
                  + 0.3 * (1 - n_red / 3)
                  + 0.2 * (1 - pe_pct)
                  + 0.2 * (1 - n_red / 3))

        e_state = row.get("expectation_state", "")
        vol_z = None
        try:
            from growth_os.expectation_state import ExpectationStateEngine
            vol_z = ExpectationStateEngine().classify(code, T_DATE).vol_z
        except Exception:
            pass
        memo = eng.generate(code, T_DATE, row["radar"], row["research_stage"],
                            row["research_priority"], row["drivers"], row["risks"],
                            expectation_state=e_state, vol_z=vol_z,
                            priority_note=str(row.get("priority_note", "")))
        rows.append({**row.to_dict(), "ra_score": round(ra, 3),
                     "n_green": n_green, "n_red": n_red,
                     "confidence": memo["confidence"],
                     "memo": eng.render_markdown(memo)})

    out = pd.DataFrame(rows)

    # Radar-Quota: Growth Top25 + Recovery Top25
    g_top = out[out["radar"] == "growth_radar"].sort_values("ra_score", ascending=False).head(25)
    r_top = out[out["radar"] == "recovery_radar"].sort_values("ra_score", ascending=False).head(25)
    top50 = pd.concat([g_top, r_top]).sort_values(["radar", "ra_score"], ascending=[True, False])

    # ---- Daily Research Book ----
    os.makedirs(OUT, exist_ok=True)
    lines = [
        "# Daily Research Book — 2026-09-01（中报后）",
        "",
        f"**研究池**: {len(df)} → **A级**: {len(out)} → **Top50**: {len(top50)}（Growth 25 + Recovery 25）",
        "",
        "## 研究队列总览",
        "",
        "| 代码 | 雷达 | L | E | 优先级 | 驱动 |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in top50.iterrows():
        drv = str(r["drivers"])[:55].replace("|", "/") if pd.notna(r["drivers"]) else ""
        lines.append(f"| {r['code']} | {r['radar']} | {r['lifecycle_state']} | "
                     f"{r.get('expectation_state', '')} | {r['research_priority']} | {drv} |")

    lines += ["", "---", "", "# 各标的研究 Memo", ""]
    for _, r in top50.iterrows():
        lines.append(r["memo"])
        lines.append("\n---\n")

    book_md = "\n".join(lines)
    with open(f"{OUT}.md", "w") as f:
        f.write(book_md)
    top50.to_csv(f"{OUT}.csv", index=False, encoding="utf-8-sig")

    logger.info(f"Daily Research Book 已生成: {OUT}.md ({len(top50)} 份 Memo)")
    print(f"\n=== 研究队列统计 ===")
    print(f"Growth Top25: RA 范围 {g_top['ra_score'].min():.2f}-{g_top['ra_score'].max():.2f}")
    print(f"Recovery Top25: RA 范围 {r_top['ra_score'].min():.2f}-{r_top['ra_score'].max():.2f}")
    print(f"green 探针均值: {top50['n_green'].mean():.1f} | red 均值: {top50['n_red'].mean():.1f}")

if __name__ == "__main__":
    main()
