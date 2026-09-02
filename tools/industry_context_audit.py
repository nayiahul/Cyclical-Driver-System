"""Step 8.2: Industry Context Layer 历史验证 — 信息增量检验。

实验设计 (严格对照):
  Group A: L5 v1 全部 (baseline)
  Group B: L5 + Industry GREEN
  Group C: L5 + Industry YELLOW
  Group D: L5 + Industry RED (Recovery Trap)

核心假设:
  H1: P(恢复 | Industry GREEN) > P(恢复 | 全部 L5)
  H2: P(失败 | Industry RED) > P(失败 | Industry GREEN)

三模块 (v1 简化, 全部 PIT 可构建):
  Cycle Turning: 行业收入YoY中位 + 行业RPS环比
  Valuation Regime: 行业PE分位变化 + 盈利质量 (v1 用行业RPS+财务代理)
  Industry Health: 行业收入/利润YoY + 亏损面 + 行业RPS

数据: baseline/discovery_audit_2022_2025.csv (12采样日)
      baseline/l5_recovery_v2.csv (1539 L5事件 + R2恢复)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from loguru import logger

from data_governance import filter_available_reports, load_tdx_raw

MIN_IND_N = 5  # 行业聚合最少股票数


def build_industry_context():
    """为每个采样日构建行业上下文 (三模块状态)。"""
    aud = pd.read_csv("baseline/discovery_audit_2022_2025.csv")
    aud["code"] = aud["code"].astype(str).str.zfill(6)
    aud["day"] = aud["day"].astype(int)

    sw = pd.read_csv("data/cache/sw_stock_industry.csv", dtype={"code": str})
    ind_map = dict(zip(sw["code"], sw["sw1"]))
    aud["ind"] = aud["code"].map(ind_map).fillna("未知")

    days = sorted(aud["day"].unique())

    # ---- 行业财务 (tdx, 每采样日 PIT) ----
    raw = load_tdx_raw()
    fin_agg = {}  # (day, ind) -> {rev_yoy, profit_yoy, loss_rate, n}
    for day in days:
        t_date = str(day)
        avail = filter_available_reports(raw, t_date)
        avail["code"] = avail["code"].astype(str).str.zfill(6)
        avail["ind"] = avail["code"].map(ind_map)
        avail = avail.dropna(subset=["ind"])
        for ind_, g in avail.groupby("ind"):
            rev = g["revenue_yoy"].dropna()
            prof = g["net_profit_yoy"].dropna()
            n = g["code"].nunique()
            if n < MIN_IND_N:
                continue
            fin_agg[(day, ind_)] = {
                "rev_yoy": rev.median() if len(rev) else np.nan,
                "profit_yoy": prof.median() if len(prof) else np.nan,
                "loss_rate": (prof < 0).mean() if len(prof) else np.nan,
                "n": n,
            }
        logger.info(f"财务聚合 {t_date}: {len([k for k in fin_agg if k[0]==day])} 行业")

    # ---- 行业 RPS (aud 截面) + 环比 ----
    ind_rps = aud.groupby(["day", "ind"])["rps"].median().unstack()
    ind_rps_chg = ind_rps.diff().fillna(0)

    # ---- 行业 PE 分位 (peTTM 截面中位分位, 简化: 用 aud 的 rps 代理估值位置) ----
    # v1: 行业 RPS 水平作为"市场认可度", 环比作为"资金回流"

    # ---- 三模块判定 ----
    ctx = {}
    for (day, ind_), f in fin_agg.items():
        rps_lvl = ind_rps.loc[day, ind_] if ind_ in ind_rps.columns else np.nan
        rps_chg = ind_rps_chg.loc[day, ind_] if ind_ in ind_rps_chg.columns else np.nan
        rev = f["rev_yoy"]
        prof = f["profit_yoy"]
        loss = f["loss_rate"]

        # Module 1: Cycle Turning
        if not np.isnan(rev) and not np.isnan(rps_chg):
            if rev > 0 and rps_chg > 0:
                cycle = "TURNING_UP"
            elif rev < -5 or rps_chg < -3:
                cycle = "TURNING_DOWN"
            else:
                cycle = "STABLE"
        else:
            cycle = "UNKNOWN"

        # Module 3: Industry Health
        if not np.isnan(prof) and not np.isnan(loss):
            if prof > 0 and loss < 0.35:
                health = "HEALTHY"
            elif prof < -5 or loss > 0.5:
                health = "STRUCTURAL_DAMAGE"
            else:
                health = "WARNING"
        else:
            health = "UNKNOWN"

        # Module 2: Valuation Regime (v1 代理: 盈利质量 + 市场认可度变化)
        if not np.isnan(prof):
            if prof < -10 and rps_chg < -5:
                regime = "STRUCTURAL_DE_RATING"
            elif prof > 0 and rps_chg > 0:
                regime = "NORMAL_DISCOUNT"
            else:
                regime = "OVERREACTION"
        else:
            regime = "UNKNOWN"

        ctx[(day, ind_)] = {
            "cycle": cycle, "health": health, "regime": regime,
            "ind_rps": rps_lvl, "ind_rps_chg": rps_chg,
            "rev_yoy": rev, "profit_yoy": prof, "loss_rate": loss,
        }
    return aud, ctx


def main():
    aud, ctx = build_industry_context()

    # ---- 合并到 L5 事件 ----
    l5 = pd.read_csv("baseline/l5_recovery_v2.csv")
    l5["code"] = l5["code"].astype(str).str.zfill(6)
    l5["day"] = l5["day"].astype(int)
    sw = pd.read_csv("data/cache/sw_stock_industry.csv", dtype={"code": str})
    ind_map = dict(zip(sw["code"], sw["sw1"]))
    l5["ind"] = l5["code"].map(ind_map).fillna("未知")

    rows = []
    for _, ev in l5.iterrows():
        c = ctx.get((ev["day"], ev["ind"]))
        if c is None:
            continue
        # 行业 Gate: 综合状态 (GREEN = 至少2模块正向, RED = 任1模块DAMAGE/DOWN)
        damage_flags = [
            c["cycle"] == "TURNING_DOWN",
            c["health"] == "STRUCTURAL_DAMAGE",
            c["regime"] == "STRUCTURAL_DE_RATING",
        ]
        up_flags = [
            c["cycle"] == "TURNING_UP",
            c["health"] == "HEALTHY",
        ]
        n_damage = sum(damage_flags)
        n_up = sum(up_flags)
        if n_damage >= 1:
            gate = "RED"
        elif n_up >= 2 or (n_up >= 1 and n_damage == 0):
            gate = "GREEN"
        else:
            gate = "YELLOW"
        rows.append({
            **ev.to_dict(), "gate": gate, "cycle": c["cycle"],
            "health": c["health"], "regime": c["regime"],
        })

    df = pd.DataFrame(rows)
    print(f"L5 事件 (有行业上下文): {len(df)} / {len(l5)} ({len(df)/len(l5):.0%} 覆盖率)")

    # ---- Group A/B/C/D 对照 ----
    print("\n" + "=" * 66)
    print("Group 对照 (Recovery R2 + 失败率)")
    print("=" * 66)
    groups = {
        "A 全部L5": df,
        "B GREEN": df[df["gate"] == "GREEN"],
        "C YELLOW": df[df["gate"] == "YELLOW"],
        "D RED": df[df["gate"] == "RED"],
    }
    for name, g in groups.items():
        r2 = g["R2_state"].dropna()
        fail = g["fwd6"].dropna()
        if len(r2):
            print(f"  {name:<12} n={len(g):>4} 恢复率={r2.mean():>6.1%} "
                  f"失败率(fwd6<-20%)={(fail<-0.2).mean():>5.1%} "
                  f"fwd6={fail.mean():>6.1%}")

    # ---- H1/H2 检验 ----
    base_r2 = df["R2_state"].mean()
    g_r2 = df[df["gate"] == "GREEN"]["R2_state"].mean()
    d_r2 = df[df["gate"] == "RED"]["R2_state"].mean()
    g_fail = df[df["gate"] == "GREEN"]["fwd6"].dropna()
    d_fail = df[df["gate"] == "RED"]["fwd6"].dropna()
    all_fail = df["fwd6"].dropna()

    print("\n=== H1: Industry GREEN 是否提高恢复率 ===")
    print(f"  基线 {base_r2:.1%} → GREEN {g_r2:.1%} (Δ {g_r2-base_r2:+.1%}) → "
          f"{'✅ 成立' if g_r2 > base_r2 else '❌ 不成立'}")
    print("=== H2: Industry RED 是否识别陷阱 ===")
    print(f"  GREEN 失败率 {(g_fail<-0.2).mean():.1%} vs RED 失败率 {(d_fail<-0.2).mean():.1%} → "
          f"{'✅ 成立' if (d_fail<-0.2).mean() > (g_fail<-0.2).mean() else '❌ 不成立'}")
    print(f"  RED 恢复率 {d_r2:.1%} vs 基线 {base_r2:.1%}")

    # ---- Train/Test ----
    df["year"] = df["day"].astype(str).str[:4]
    print("\n=== Train/Test 稳定性 ===")
    for label, mask in [("2022-2023", df["year"].isin(["2022","2023"])),
                        ("2024-2025", df["year"].isin(["2024","2025"]))]:
        sub = df[mask]
        b = sub["R2_state"].mean()
        g = sub[sub["gate"] == "GREEN"]["R2_state"].mean() if len(sub[sub["gate"] == "GREEN"]) else np.nan
        d = sub[sub["gate"] == "RED"]["R2_state"].mean() if len(sub[sub["gate"] == "RED"]) else np.nan
        print(f"  {label}: 基线 {b:.1%} | GREEN {g:.1%} | RED {d:.1%} (n={len(sub)})")

    # ---- 六案例回放 ----
    print("\n=== 六案例回放 ===")
    for code, name in [("300308","中际旭创"),("605499","东鹏饮料"),("603486","科沃斯"),
                       ("000425","徐工机械"),("002192","融捷股份")]:
        sub = df[df["code"] == code]
        if len(sub):
            r = sub.iloc[0]
            print(f"  {code} {name}: gate={r['gate']} cycle={r['cycle']} "
                  f"health={r['health']} regime={r['regime']}")

    df.to_csv("baseline/industry_context_audit.csv", index=False)
    print(f"\n已保存 baseline/industry_context_audit.csv ({len(df)} 行)")


if __name__ == "__main__":
    main()
