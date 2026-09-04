"""G0-A B_proxy Coverage Probe — 4 Pilot t0 覆盖率实测 (Gate 0 关闭前最后勘察)。

目的: 把 B_v35 / B_legacy 的 OK/WEAK/UNKNOWN 覆盖率 + margin yellow 占比 + 实际交易日钉死。
依据: diagnostics/B_PROXY_FIELD_MAPPING.md §5 G0-A/G0-B
性质: 数据勘察, 非实验 — 不产生投资结论。
"""
import sys
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np
import pandas as pd
from loguru import logger

from data_governance import filter_available_reports
from trade_calendar import get_trade_calendar

T0_CANDIDATES = ["20230510", "20231110", "20240910", "20250510"]


def resolve_t0(d: str, cal) -> str:
    """非交易日 → 顺延下一交易日 (G0-B)。"""
    dates = cal["trade_date"].tolist()
    if d in dates:
        return d
    after = [x for x in dates if x > d]
    return after[0] if after else d


def main():
    # G0-B: 交易日确认
    cal = get_trade_calendar("20230101", "20251231")
    resolved = {d: resolve_t0(d, cal) for d in T0_CANDIDATES}
    for d, r in resolved.items():
        flag = "" if d == r else f" ← 顺延 (非交易日)"
        logger.info(f"t0 {d} → {r}{flag}")

    # 财务全表
    raw = pd.read_csv("data/cache/tdx_financials.csv",
                      dtype={"code": str, "report_date_str": str})
    raw["code"] = raw["code"].astype(str).str.zfill(6)
    logger.info(f"TDX 全表: {len(raw)} 行 / {raw['code'].nunique()} 只")

    # Legacy: financial_data.csv (akshare 源)
    leg_path = "data/cache/financial_data.csv"
    leg = None
    if os.path.exists(leg_path):
        leg = pd.read_csv(leg_path, dtype={"code": str})
        leg["code"] = leg["code"].astype(str).str.zfill(6)
        leg["date"] = pd.to_datetime(leg["date"]).dt.strftime("%Y%m%d")
        logger.info(f"Legacy 表: {len(leg)} 行 / {leg['code'].nunique()} 只")
    else:
        logger.warning("financial_data.csv 不存在 → legacy 覆盖率全 0")

    rows = []
    for cand, t0 in resolved.items():
        avail = filter_available_reports(raw, t0)
        avail = avail.sort_values("report_date_str").groupby("code").tail(8)
        n_univ = avail["code"].nunique()

        # --- B_v35: margin green? + ROIC>0 ---
        # 近似探针语义: 需 >=8 期 gross_margin 判定; 用 tail(8) 简化:
        # 精确探针需逐股 gm_recent/gm_old/gm_std — 此处为覆盖率勘察, 用可得性近似:
        gm_avail = avail.groupby("code")["gross_margin"].apply(
            lambda s: s.dropna().tail(12))
        # 逐股: 最近4季均 / 前4季均 / std
        def margin_state(g):
            s = g.dropna().tail(12)
            if len(s) < 8:
                return "unknown"
            gm_recent = s.iloc[-4:].mean()
            gm_old = s.iloc[-8:-4].mean()
            gm_trend = gm_recent - gm_old
            gm_std = s.std()
            if gm_recent > 35 and gm_trend > 0:
                return "green"
            if gm_recent > 30 and abs(gm_trend) < 2:
                return "green"
            if gm_trend < -3 or gm_std > 8:
                return "red"
            return "yellow"

        g = avail.groupby("code")
        margin_st = g.apply(lambda df: margin_state(df["gross_margin"]))
        # rev_yoy>20 路径需额外字段 — 覆盖率勘察阶段放宽 (标注)
        def _last_pos(s):
            v = pd.Series(s).dropna()
            return bool((v > 0).any()) if len(v) else None
        roic_pos = g.apply(lambda df: _last_pos(df["roic"]))

        n = len(margin_st)
        # 四态分类 (field mapping 决策点): yellow+roic>0 单列观察层, 不计入 OK/WEAK
        def classify(m_lv, r_pos):
            if m_lv == "unknown" or r_pos is None:
                return "unknown"
            if m_lv == "green" and r_pos:
                return "ok"
            if m_lv == "yellow" and r_pos:
                return "yellow"
            return "weak"  # red 或 roic<=0

        b_class = [classify(m, r) for m, r in zip(margin_st, roic_pos)]
        b_ok = b_class.count("ok")
        b_weak = b_class.count("weak")
        b_yellow = b_class.count("yellow")
        b_unknown = b_class.count("unknown")

        # --- B_legacy: roe 8期可得 + ocf 最新>0 ---
        # 注意: 不在 legacy 表内的 code (3406 只之外 ~1800 只) 必须算 UNKNOWN
        leg_ok = leg_weak = leg_unknown = 0
        if leg is not None:
            lf_all = leg[leg["date"] <= t0]
            leg_codes = set(lf_all["code"])
            lc = lf_all.groupby("code")
            roe_n = lc.apply(lambda d: len(pd.Series(d["roe_weighted"]).dropna().tail(12)))
            ocf_pos = lc.apply(lambda df: _last_pos(df["ocf_to_revenue"]))
            roe_n_map, ocf_pos_map = roe_n.to_dict(), ocf_pos.to_dict()
            for c in margin_st.index:
                if c not in leg_codes:
                    leg_unknown += 1
                    continue
                rn = roe_n_map.get(c, 0)
                op = ocf_pos_map.get(c)
                if rn >= 8 or op is True:
                    leg_ok += 1
                elif op is False:
                    leg_weak += 1
                else:
                    leg_unknown += 1
            leg_n = len(margin_st)

        rows.append({
            "t0": t0, "candidate": cand, "universe_n": n_univ,
            "margin_unknown": int(sum(margin_st == "unknown")),
            "margin_green": int(sum(margin_st == "green")),
            "margin_yellow": int(sum(margin_st == "yellow")),
            "margin_red": int(sum(margin_st == "red")),
            "roic_pos": int(sum(roic_pos == True)), "roic_nonpos_or_na": int(n - sum(roic_pos == True)),
            "b_v35_ok": int(b_ok), "b_v35_weak": int(b_weak), "b_v35_yellow": int(b_yellow),
            "b_v35_unknown": int(b_unknown),
            "legacy_ok": int(leg_ok), "legacy_weak": int(leg_weak),
            "legacy_unknown": int(leg_unknown), "legacy_n": leg_n,
        })
        logger.info(f"t0 {t0}: univ {n_univ} | v35 OK {b_ok} WEAK {b_weak} YELLOW {b_yellow} UNK {b_unknown} "
                    f"| legacy OK {leg_ok} WEAK {leg_weak} UNK {leg_unknown}")

    out = pd.DataFrame(rows)
    for c in out.columns:
        if out[c].dtype == "object":
            out[c] = out[c].astype(str)
    # 百分比行
    for i, r in out.iterrows():
        n = r["universe_n"]
        out.loc[i, "b_v35_ok_pct"] = round(r["b_v35_ok"] / n * 100, 1) if n else 0
        out.loc[i, "b_v35_weak_pct"] = round(r["b_v35_weak"] / n * 100, 1) if n else 0
        out.loc[i, "b_v35_yellow_pct"] = round(r["b_v35_yellow"] / n * 100, 1) if n else 0
        out.loc[i, "b_v35_unknown_pct"] = round(r["b_v35_unknown"] / n * 100, 1) if n else 0
        out.loc[i, "legacy_unknown_pct"] = round(r["legacy_unknown"] / n * 100, 1) if n else 0
    out.to_csv("diagnostics/b_proxy_coverage_probe.csv", index=False)
    logger.info("已输出 diagnostics/b_proxy_coverage_probe.csv")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
