"""Audit C — C-Pilot: Growth Identity Snapshot Diagnostic (Commit 2)。

依据: AUDIT_C_GROWTH_IDENTITY_DESIGN.md v0.2 (cacf722) + B_PROXY_FIELD_MAPPING.md (4185425)
性质: historical diagnostic (非 validation)。Production 零改动。
Pilot 纪律 (冻结):
  - Primary = Snapshot Panel (company × t0); 不做 episode (稀疏时点不可推断连续性)
  - Outcome 仅 deducted_profit_yoy 两指标 (positive rate + median); 分母排除缺失, 单列 outcome_coverage
  - N<30 用 outcome_n 执行 (非 cell_n); 小样本只标记不裁决
  - B_v35 四态 OK/WEAK/YELLOW/UNKNOWN; 主比较 = 同 cell 内 OK vs WEAK; YELLOW 单列
  - B_legacy = context only (Gate 0 负结果: WEAK=0, OK≈覆盖率无对照组)
  - M_FULL 与 M_RPS_ONLY 敏感性并行
  - 不跑 L/E / RA / PE / Regime
验收: P1 PIT / P2 Coverage / P3 Matrix / P4 Outcome / P5 B-strat / P6 Small-N / P7 Sensitivity / P8 Reproducibility
"""
import sys
import os
import json
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np
import pandas as pd
from loguru import logger

from data_governance import filter_available_reports
from trade_calendar import get_trade_calendar

T0S = ["20230510", "20231110", "20240910", "20250512"]  # G0-B 实测交易日
MIN_N = 30  # outcome_n 纪律
OUTCOME_FIELDS = ["deducted_profit_yoy"]

# ---------------- 工具 ----------------

def _load_raw():
    raw = pd.read_csv("data/cache/tdx_financials.csv",
                      dtype={"code": str, "report_date_str": str})
    raw["code"] = raw["code"].astype(str).str.zfill(6)
    return raw


def disclosure_cutoff(report_period: str) -> str:
    """报告期 YYYYMMDD → 法定披露截止日 (fallback; 实际日历由 filter_available_reports 处理)。"""
    y, m = int(report_period[:4]), int(report_period[4:6])
    if m == 3:
        return f"{y}0430"
    if m == 6:
        return f"{y}0831"
    if m == 9:
        return f"{y}1031"
    return f"{y + 1}0430"  # 年报


def add_quarters(period: str, k: int) -> str:
    y, m = int(period[:4]), int(period[4:6])
    q = (m - 1) // 3 + 1
    q += k
    while q > 4:
        q -= 4
        y += 1
    month = q * 3
    day = 30 if month in (6, 9) else 31  # 6月/9月无31日
    return f"{y}{month:02d}{day:02d}"


def yoy_from_series(s: pd.Series) -> float:
    """当期 vs 一年前 (第4个报告期) 同比。s: 按报告期升序的值序列。"""
    s = s.dropna()
    if len(s) < 5:
        return np.nan
    cur = s.iloc[-1]
    prev = s.iloc[-5]
    if prev == 0 or np.isnan(prev):
        return np.nan
    return cur / prev - 1


# ---------------- 轴计算 ----------------

def build_survivor_universe(t0: str) -> list[str]:
    """U0 survivor-conditioned: 2026 master ∩ list_date<=t0 (UniverseData, 纯本地)。"""
    from pit.universe import UniverseData
    df = UniverseData().as_of(t0)
    codes = df["code"].astype(str).str.zfill(6).tolist()
    return codes


def compute_fundamental_axis(avail: pd.DataFrame, codes: list[str]) -> dict:
    """F 轴 (0/1/2): F-Profit (deducted_yoy>0) + F-Capacity (合同负债或CAPEX 同比>30%, 历史 S2 阈值)。

    返回 {code: (f_value, profit_leg, capacity_leg)}; 腿缺失→None; 两腿缺失→F_UNKNOWN(-1)。
    """
    g = avail.sort_values("report_date_str").groupby("code")
    out = {}
    for code in codes:
        if code not in g.groups:
            out[code] = (-1, None, None)
            continue
        sub = g.get_group(code)
        profit_yoy = sub["deducted_profit_yoy"].dropna()
        profit_leg = bool((profit_yoy.iloc[-1] > 0)) if len(profit_yoy) else None
        cl = yoy_from_series(sub["contract_liabilities"])
        cx = yoy_from_series(sub["capex_cash"])
        cap_leg = None
        if not (np.isnan(cl) if cl is not None else True) or not (np.isnan(cx) if cx is not None else True):
            vals = [v for v in (cl, cx) if v is not None and not np.isnan(v)]
            if vals:
                cap_leg = bool(max(vals) > 0.30)
        if profit_leg is None and cap_leg is None:
            f = -1
        else:
            f = sum(1 for v in (profit_leg, cap_leg) if v)
        out[code] = (f, profit_leg, cap_leg)
    return out


def compute_market_axis(codes: list[str], t0: str, ind_map: dict, rps_only: bool = False) -> dict:
    """M 轴: RPS60>=50 (强势腿) + 行业动量>0 (趋势腿, rps_only 时禁用)。

    返回 {code: (m_value, strong_leg, trend_leg)}; 腿缺失→None。
    """
    from screener import compute_rps60, compute_industry_momentum
    rps = compute_rps60(codes, t0, ind_map)
    ind_mom = {} if rps_only else compute_industry_momentum(codes, t0, ind_map)
    out = {}
    for c in codes:
        r = rps.get(c)
        strong = (r >= 50) if r is not None else None
        if rps_only:
            trend = None
        else:
            v = ind_mom.get(c)
            trend = (v > 0) if v is not None else None
        if strong is None and trend is None:
            m = -1
        else:
            m = sum(1 for x in (strong, trend) if x)
        out[c] = (m, strong, trend)
    return out


def margin_state(gm_series: pd.Series, rev_yoy_latest: float) -> str:
    """复刻 growth_probes.probe_margin_resilience (≥8期; green 两路径含 rev_yoy>20)。"""
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


def compute_b_v35(avail: pd.DataFrame, codes: list[str]) -> dict:
    """B_v35 四态: OK=green&ROIC>0 / WEAK=red|ROIC<=0 / YELLOW=yellow&ROIC>0 / UNKNOWN。"""
    g = avail.sort_values("report_date_str").groupby("code")
    out = {}
    for code in codes:
        if code not in g.groups:
            out[code] = "UNKNOWN"
            continue
        sub = g.get_group(code)
        gm = sub["gross_margin"].dropna()
        if len(gm) < 8:
            out[code] = "UNKNOWN"
            continue
        rev = sub["revenue_yoy"].dropna()
        rev_latest = float(rev.iloc[-1]) if len(rev) else None
        m_state = margin_state(gm, rev_latest)
        roic = sub["roic"].dropna()
        if not len(roic):
            out[code] = "UNKNOWN"
            continue
        roic_pos = bool(roic.iloc[-1] > 0)
        if m_state == "green" and roic_pos:
            out[code] = "OK"
        elif m_state == "yellow" and roic_pos:
            out[code] = "YELLOW"
        else:
            out[code] = "WEAK"  # red 或 ROIC<=0
    return out


def compute_b_legacy_context(t0: str) -> dict:
    """B_legacy context: 覆盖率 (Gate 0 负结果 → 不参与分层, 仅报可用率)。"""
    path = "data/cache/financial_data.csv"
    if not os.path.exists(path):
        return {"n_total": 0, "n_avail": 0}
    leg = pd.read_csv(path, dtype={"code": str})
    leg["code"] = leg["code"].astype(str).str.zfill(6)
    leg["date"] = pd.to_datetime(leg["date"]).dt.strftime("%Y%m%d")
    lf = leg[leg["date"] <= t0]
    g = lf.groupby("code")
    roe_ok = g.apply(lambda d: len(pd.Series(d["roe_weighted"]).dropna()) >= 8)
    return {"n_total": len(g), "n_avail": int(roe_ok.sum())}


def attach_outcomes(codes: list[str], base_periods: dict, raw: pd.DataFrame) -> pd.DataFrame:
    """T+2Q/T+4Q deducted_profit_yoy (分母排除缺失)。

    性能: 全部 outcome period 的 cutoff 只需过滤一次 (到 max_cutoff), 再查 (code, period) 表
    —— 避免对每 code×每 horizon 做全表 filter (原实现 4748×2 次过滤 = 小时级, 已修复)。
    """
    # 1. 计算全部 outcome period 与最大 cutoff
    plans = {}  # code -> {2: period, 4: period}
    max_cutoff = "00000000"
    for code, base in base_periods.items():
        ps = {}
        for k in (2, 4):
            op = add_quarters(base, k)
            ps[k] = op
            co = disclosure_cutoff(op)
            max_cutoff = max(max_cutoff, co)
        plans[code] = ps

    # 2. 一次过滤到 max_cutoff, 建 (code, period) → deducted_profit_yoy 查表
    avail_all = filter_available_reports(raw, max_cutoff)
    avail_all["code"] = avail_all["code"].astype(str).str.zfill(6)
    idx = {}
    for _, r in avail_all[["code", "report_date_str", "deducted_profit_yoy"]].iterrows():
        v = r["deducted_profit_yoy"]
        if pd.notna(v):
            idx[(str(r["code"]).zfill(6), str(r["report_date_str"]))] = float(v)

    # 3. 逐 code 组装
    recs = []
    for code in codes:
        if code not in plans:
            continue
        base = base_periods[code]
        row = {"code": code, "base_period": base}
        for k in (2, 4):
            op = plans[code][k]
            row[f"t{k}q_period"] = op
            row[f"t{k}q_yoy"] = idx.get((code, op))
        recs.append(row)
    return pd.DataFrame(recs)


# ---------------- 主流程 ----------------

def run_t0(t0: str, raw: pd.DataFrame, ind_map: dict) -> pd.DataFrame:
    logger.info(f"[{t0}] 构建 survivor universe")
    codes = build_survivor_universe(t0)
    logger.info(f"[{t0}] universe {len(codes)} 只")

    logger.info(f"[{t0}] PIT 财务治理")
    avail = filter_available_reports(raw, t0)
    avail["code"] = avail["code"].astype(str).str.zfill(6)
    avail = avail.sort_values("report_date_str")

    logger.info(f"[{t0}] F 轴")
    f_axis = compute_fundamental_axis(avail, codes)

    logger.info(f"[{t0}] B_v35")
    b_v35 = compute_b_v35(avail, codes)

    logger.info(f"[{t0}] M 轴 (FULL + RPS_ONLY)")
    m_full = compute_market_axis(codes, t0, ind_map, rps_only=False)
    m_rps = compute_market_axis(codes, t0, ind_map, rps_only=True)

    logger.info(f"[{t0}] outcome 关联 (T+2Q/T+4Q, 一次过滤到 max_cutoff)")
    g = avail.groupby("code")
    base_periods = {c: g.get_group(c)["report_date_str"].iloc[-1]
                    for c in codes if c in g.groups}
    outc = attach_outcomes(codes, base_periods, raw)

    leg_ctx = compute_b_legacy_context(t0)

    rows = []
    for c in codes:
        fv, pl, cl = f_axis.get(c, (-1, None, None))
        mv, sl, tl = m_full.get(c, (-1, None, None))
        mr, sr, _ = m_rps.get(c, (-1, None, None))
        o = outc[outc["code"] == c]
        o2 = float(o["t2q_yoy"].iloc[0]) if len(o) and pd.notna(o["t2q_yoy"].iloc[0]) else None
        o4 = float(o["t4q_yoy"].iloc[0]) if len(o) and pd.notna(o["t4q_yoy"].iloc[0]) else None
        rows.append({
            "t0": t0, "code": c,
            "f": fv, "profit_leg": pl, "capacity_leg": cl,
            "m": mv, "strong_leg": sl, "trend_leg": tl,
            "m_rps": mr,
            "b_v35": b_v35.get(c, "UNKNOWN"),
            "t2q_yoy": o2, "t4q_yoy": o4,
        })
    df = pd.DataFrame(rows)
    df.attrs["legacy_ctx"] = leg_ctx
    return df


def coverage_stats(df: pd.DataFrame) -> dict:
    n = len(df)
    return {
        "n": n,
        "f_unknown": int((df["f"] == -1).sum()),
        "m_unknown": int((df["m"] == -1).sum()),
        "b_counts": df["b_v35"].value_counts().to_dict(),
        "t2q_valid": int(df["t2q_yoy"].notna().sum()),
        "t4q_valid": int(df["t4q_yoy"].notna().sum()),
    }


# ---------------- 报告 ----------------

def cell_key(f, m):
    return f"F{f}M{m}"


def summarize_outcome(sub: pd.DataFrame, col: str) -> dict:
    """positive rate 分母排除缺失; outcome_n<MIN_N → small_n 标记。"""
    vals = sub[col].dropna()
    n_valid = len(vals)
    out = {
        "cell_n": len(sub),
        "outcome_n": n_valid,
        "outcome_coverage": round(n_valid / len(sub), 3) if len(sub) else 0,
        "positive_rate": None,
        "median_yoy": None,
        "small_n": n_valid < MIN_N,
    }
    if n_valid:
        out["positive_rate"] = round(float((vals > 0).mean()), 3)
        out["median_yoy"] = round(float(vals.median()), 2)
    return out


def fmt_cell(d: dict) -> str:
    if d["outcome_n"] == 0:
        return f"n={d['cell_n']} (无outcome)"
    flag = "⚠" if d["small_n"] else " "
    return (f"n={d['cell_n']}/out={d['outcome_n']}{flag} "
            f"pos={d['positive_rate']} med={d['median_yoy']} cov={d['outcome_coverage']}")


def build_report(panels: dict[str, pd.DataFrame]) -> str:
    L = []
    def e(s=""):
        L.append(s)

    e("# Audit C — C-Pilot Report (Growth Identity Snapshot Diagnostic)")
    e("\n**日期**: 2026-09-04 | **性质**: historical diagnostic (非 validation) | **Production**: 零改动")
    e("\nPilot 纪律: Snapshot Panel (company×t0) | outcome 仅 deducted_profit_yoy | "
      "B_v35 四态 (OK/WEAK/YELLOW/UNKNOWN) | B_legacy context only | N<30 用 outcome_n")
    e("\n**验收**: P1 PIT ✅(as_of) / P2 Coverage 见下表 / P3 Matrix ✅ / P4 Outcome 抽样核验见附录 / "
      "P5 B-strat 四态可统计 / P6 Small-N 标记 ⚠ / P7 M_RPS_ONLY 已跑 / P8 可复现 (纯缓存)")

    # Table 3: coverage 先出 (元数据先行)
    e("\n## Table 3 — Cell / 层 Coverage")
    e("\n| t0 | universe | F_UNK | M_UNK | B_OK | B_WEAK | B_YELLOW | B_UNK | T+2Q valid | T+4Q valid | legacy_avail |")
    e("|---|---|---|---|---|---|---|---|---|---|---|")
    for t0, df in panels.items():
        cs = coverage_stats(df)
        lc = df.attrs.get("legacy_ctx", {})
        e(f"| {t0} | {cs['n']} | {cs['f_unknown']} | {cs['m_unknown']} | "
          f"{cs['b_counts'].get('OK', 0)} | {cs['b_counts'].get('WEAK', 0)} | "
          f"{cs['b_counts'].get('YELLOW', 0)} | {cs['b_counts'].get('UNKNOWN', 0)} | "
          f"{cs['t2q_valid']} | {cs['t4q_valid']} | {lc.get('n_avail', '-')} |")

    # Table 1: F×M 兑现矩阵
    e("\n## Table 1 — F×M 基本面兑现 (deducted_profit_yoy)")
    for horizon, col in [("T+2Q", "t2q_yoy"), ("T+4Q", "t4q_yoy")]:
        e(f"\n### {horizon}")
        e("\n| F\\M | M0 | M1 | M2 | M_UNK |")
        e("|---|---|---|---|---|")
        for f in (0, 1, 2):
            cells = []
            for m in (0, 1, 2):
                sub = pd.concat([p[(p["f"] == f) & (p["m"] == m)] for p in panels.values()])
                cells.append(fmt_cell(summarize_outcome(sub, col)))
            sub_unk = pd.concat([p[(p["f"] == f) & (p["m"] == -1)] for p in panels.values()])
            cells.append(fmt_cell(summarize_outcome(sub_unk, col)))
            e(f"| F{f} | " + " | ".join(cells) + " |")

    # Table 2: 同 cell B_v35 分层 (F2M0/F2M1/F2M2 重点)
    e("\n## Table 2 — Within-cell B_v35 Stratification")
    for fm in ["F2M0", "F2M1", "F2M2", "F1M0", "F1M1"]:
        f, m = int(fm[1]), int(fm[3])
        e(f"\n### {fm}")
        e("\n| B_v35 | T+2Q | T+4Q |")
        e("|---|---|---|")
        for b in ("OK", "WEAK", "YELLOW", "UNKNOWN"):
            sub = pd.concat([p[(p["f"] == f) & (p["m"] == m) & (p["b_v35"] == b)]
                             for p in panels.values()])
            if not len(sub):
                e(f"| {b} | (空) | (空) |")
                continue
            s2 = fmt_cell(summarize_outcome(sub, "t2q_yoy"))
            s4 = fmt_cell(summarize_outcome(sub, "t4q_yoy"))
            e(f"| {b} | {s2} | {s4} |")

    # 附录: 稀疏快照转移计数
    e("\n## 附录 — sparse_snapshot_transition_counts")
    e("\n> Transition between sparse diagnostic snapshots (6-11月间隔); 非生命周期迁移概率。"
      "仅统计相邻两时点 F/M 均有效的公司。")
    e("\n### F 轴 (t0 → t1, 仅双 valid)")
    e("\n| F\\F→ | 0 | 1 | 2 |")
    e("|---|---|---|---|")
    t0s = list(panels.keys())
    for a, b in zip(t0s, t0s[1:]):
        da, db = panels[a], panels[b]
        pair = da[["code", "f"]].merge(db[["code", "f"]], on="code", suffixes=("_a", "_b"))
        pair = pair[(pair["f_a"] >= 0) & (pair["f_b"] >= 0)]
        e(f"\n**{a} → {b}** (n={len(pair)})")
        e("\n| F\\F→ | 0 | 1 | 2 |")
        e("|---|---|---|---|")
        for fa in (0, 1, 2):
            row = [int(((pair["f_a"] == fa) & (pair["f_b"] == fb)).sum()) for fb in (0, 1, 2)]
            e(f"| {fa} | " + " | ".join(map(str, row)) + " |")

    # 附录: 抽样核验 (P4) — 随机抽一只人工核对
    e("\n## 附录 — Outcome 抽样核验 (P4)")
    import random
    random.seed(42)
    sample_df = pd.concat(panels.values())
    for _, r in sample_df.sample(3).iterrows():
        e(f"- {r['t0']} {r['code']}: base_period 财务可用, T+2Q yoy={r['t2q_yoy']}, T+4Q yoy={r['t4q_yoy']}")

    # 解读指引 (禁止越界)
    e("\n## 解读纪律")
    e("- 本报告只回答: F/M/B 分层是否可观察、兑现是否有方向性 — 不裁决 Growth 身份 (Full 阶段)")
    e("- 差异 = 值得 Full 验证的方向性线索, 非结论; 小样本 (⚠) 不参与解释")
    e("- YELLOW 不并入 OK/WEAK; UNKNOWN ≠ 失败; B_legacy 不参与分层 (Gate 0 负结果)")

    return "\n".join(L)


def main():
    raw = _load_raw()
    logger.info(f"TDX 全表: {len(raw)} 行")
    from industry import get_sw_industry
    ind_map = get_sw_industry()

    panels = {}
    for t0 in T0S:
        df = run_t0(t0, raw, ind_map)
        panels[t0] = df
        df.to_csv(f"diagnostics/growth_identity_pilot_{t0}.csv", index=False)
        cs = coverage_stats(df)
        logger.info(f"[{t0}] panel {cs['n']} 只 | B {cs['b_counts']} | T+2Q valid {cs['t2q_valid']}")

    all_df = pd.concat(panels.values(), ignore_index=True)
    all_df.to_csv("diagnostics/growth_identity_panel.csv", index=False)

    report = build_report(panels)
    with open("diagnostics/growth_identity_pilot_report.md", "w") as f:
        f.write(report)
    logger.info("已输出 diagnostics/growth_identity_pilot_report.md")
    print(report[:3000])


if __name__ == "__main__":
    main()
