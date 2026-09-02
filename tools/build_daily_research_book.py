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
        e2_attn, e2_ps = "", ""
        try:
            from growth_os.expectation_state import ExpectationStateEngine, ExpectationV2Shadow
            vol_z = ExpectationStateEngine().classify(code, T_DATE).vol_z
            e2r = ExpectationV2Shadow().classify(code, T_DATE)
            e2_attn, e2_ps = e2r.attention, e2r.price_state
        except Exception:
            pass
        memo = eng.generate(code, T_DATE, row["radar"], row["research_stage"],
                            row["research_priority"], row["drivers"], row["risks"],
                            expectation_state=e_state, vol_z=vol_z,
                            priority_note=str(row.get("priority_note", "")),
                            e2_attention=e2_attn,
                            e2_price_state=e2_ps)
        rows.append({**row.to_dict(), "ra_score": round(ra, 3),
                     "n_green": n_green, "n_red": n_red,
                     "confidence": memo["confidence"],
                     "memo": eng.render_markdown(memo)})

    out = pd.DataFrame(rows)

    # Radar-Quota: Growth Top25 + Recovery Top25
    g_top = out[out["radar"] == "growth_radar"].sort_values("ra_score", ascending=False).head(25)
    r_top = out[out["radar"] == "recovery_radar"].sort_values("ra_score", ascending=False).head(25)
    top50 = pd.concat([g_top, r_top]).sort_values(["radar", "ra_score"], ascending=[True, False])

    # ---- P Shadow 标注 (Step 11-D: 只观察不决策) ----
    try:
        from growth_os.paradigm_shadow import ParadigmShadowLayer
        psh = ParadigmShadowLayer()
        # discovery 从 drivers 无法反推 → 直接以 drivers 含'订单'标记近似
        out["_disc_approx"] = out["drivers"].str.contains("订单|需求漏斗", na=False).astype(float)
        top50 = psh.annotate(top50, T_DATE)
        # 按 code 合并 discovery 近似
        disc_map = dict(zip(out["code"].astype(str).str.zfill(6), out["_disc_approx"]))
        top50["_disc"] = top50["code"].astype(str).str.zfill(6).map(disc_map)
        # 用真实探针评估 (重算核心标的)
        from growth_os.paradigm_shadow import AI_OPTICAL_CORE
        core = [c for c in top50["code"].astype(str).str.zfill(6) if c in AI_OPTICAL_CORE]
        for c in core:
            import numpy as np
            from growth_os.growth_probes import probe_order_leadership, probe_capex_efficiency, probe_margin_resilience
            ps = [probe_order_leadership(c, T_DATE), probe_capex_efficiency(c, T_DATE),
                  probe_margin_resilience(c, T_DATE)]
            disc = float(np.mean([1.0 if p["level"]=="green" else 0.5 if p["level"]=="yellow" else 0.0 for p in ps]))
            r = psh.evaluate(c, T_DATE, disc)
            mask = top50["code"].astype(str).str.zfill(6) == c
            top50.loc[mask, "paradigm"] = r.paradigm
            top50.loc[mask, "p_state"] = f"P{r.p_state}"
            top50.loc[mask, "p_evidence"] = "; ".join(r.evidence)
            top50.loc[mask, "p_broken"] = "; ".join(r.broken_flags)
        logger.info(f"P Shadow 标注: {len(top50[top50['paradigm']=='AI_OPTICAL_CYCLE'])} 只 AI_OPTICAL")
    except Exception as e:
        logger.warning(f"P Shadow 标注失败: {e}")

    # ---- P Shadow 观察区 (Step 11-D: 即使 L0 也列出, 只观察不决策) ----
    shadow_rows = []
    try:
        from growth_os.paradigm_shadow import ParadigmShadowLayer, AI_OPTICAL_CORE
        import numpy as np
        from growth_os.growth_probes import probe_order_leadership, probe_capex_efficiency, probe_margin_resilience
        psh = ParadigmShadowLayer()
        pool_all = pd.read_csv(POOL)
        pool_all["code"] = pool_all["code"].astype(str).str.zfill(6)
        for code in AI_OPTICAL_CORE:
            # 全池中找该标的
            prow = pool_all[pool_all["code"] == code]
            ps = [probe_order_leadership(code, T_DATE),
                  probe_capex_efficiency(code, T_DATE),
                  probe_margin_resilience(code, T_DATE)]
            disc = float(np.mean([1.0 if p["level"]=="green" else 0.5 if p["level"]=="yellow" else 0.0 for p in ps]))
            r = psh.evaluate(code, T_DATE, disc)
            shadow_rows.append({
                "code": code, "name": AI_OPTICAL_CORE[code],
                "L": prow["lifecycle_state"].values[0] if len(prow) else "L0",
                "E": prow["expectation_state"].values[0] if len(prow) and "expectation_state" in prow else "?",
                "sys_pri": prow["research_priority"].values[0] if len(prow) else "C(压制)",
                "P": f"P{r.p_state}", "disc": round(disc, 2),
                "broken": "; ".join(r.broken_flags) if r.broken_flags else "无",
            })
        logger.info(f"P Shadow 观察区: {len(shadow_rows)} 只 AI_OPTICAL 核心")
    except Exception as e:
        logger.warning(f"P Shadow 观察区失败: {e}")

    # ---- E v2 Shadow 旁路标注 (Step 12-C: 展示不决策) ----
    try:
        from growth_os.expectation_state import ExpectationV2Shadow
        e2 = ExpectationV2Shadow()
        top50["e2_attention"] = ""
        top50["e2_expectation"] = ""
        top50["e2_price_state"] = ""
        for idx in top50.index:
            c = str(top50.loc[idx, "code"]).zfill(6)
            r = e2.classify(c, T_DATE)
            top50.loc[idx, "e2_attention"] = r.attention
            top50.loc[idx, "e2_expectation"] = r.expectation
            top50.loc[idx, "e2_price_state"] = r.price_state
        n_high = (top50["e2_attention"].str.contains("A2|A3")).sum()
        logger.info(f"E v2 Shadow: {n_high} 只高关注(非E0真忽略)")
    except Exception as e:
        logger.warning(f"E v2 Shadow 失败: {e}")

    # ---- Daily Research Book ----
    os.makedirs(OUT, exist_ok=True)
    lines = [
        "# Daily Research Book — 2026-09-01（中报后）",
        "",
        f"**研究池**: {len(df)} → **A级**: {len(out)} → **Top50**: {len(top50)}（Growth 25 + Recovery 25）",
        "",
        "## 研究队列总览",
        "",
        "| 代码 | 雷达 | L | E v1 | Attention | E v2 | Price | P | 优先级 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in top50.iterrows():
        drv = str(r["drivers"])[:40].replace("|", "/") if pd.notna(r["drivers"]) else ""
        attn = str(r.get("e2_attention", "")).replace("A2高关注", "A2").replace("A3极热", "A3")
        attn = attn.replace("A0未关注", "A0").replace("A1初始", "A1")
        exp2 = str(r.get("e2_expectation", "")).replace("E3已透支", "E3").replace("E2高预期", "E2")
        exp2 = exp2.replace("E1部分定价", "E1").replace("E0未定价", "E0")
        ps = str(r.get("e2_price_state", "")).replace("PS0新高区", "PS0").replace("PS1正常", "PS1")
        ps = ps.replace("PS2回撤", "PS2").replace("PS3深度回撤", "PS3")
        p_ = r.get("paradigm", "") if "paradigm" in r else ""
        p_state = f"{p_} {r.get('p_state', '')}" if p_ else "—"
        lines.append(f"| {r['code']} | {r['radar']} | {r['lifecycle_state']} | "
                     f"{r.get('expectation_state', '')} | {attn} | {exp2} | {ps} | {p_state} | "
                     f"{r['research_priority']} |")

    if shadow_rows:
        lines += ["", "---", "", "## P Shadow 观察区（Step 11-D: 只观察不决策）",
                  "", "| 代码 | 名称 | L | E | 系统优先级 | P状态 | discovery | Broken |",
                  "|---|---|---|---|---|---|---|---|"]
        for srow in shadow_rows:
            lines.append(f"| {srow['code']} | {srow['name']} | {srow['L']} | {srow['E']} | "
                         f"{srow['sys_pri']} | {srow['P']} | {srow['disc']:.2f} | {srow['broken']} |")
        lines += ["", "> Shadow 模式: 标签附加, Priority 不改变。30 天观察期 (2026-09-02 ~ 10-02)。", ""]

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
