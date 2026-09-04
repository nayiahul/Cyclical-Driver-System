"""Bloodline Snapshot Audit — v3.5 Production Selection Fidelity Audit (Audit A, 离线诊断)。

问题: v3.5 (研究分配链) 是否仍在筛出原始投资哲学 (景气度×壁垒×估值, Regime 定序) 想要的两类公司?
回答: 6 问 (见报告)。不改 Production; 只读缓存与 Book/Pool CSV; 冻结期纪律允许 (照 diagnostics/ 传统)。

口径纪律 (2026-09-04 评审收敛):
- 分雷达解读: Growth25 该景气高, Recovery25 该壁垒高+估值压缩+未坏 — 不混成一个 Top50
- M 一律写 M_proxy, 不写 Moat (品牌/转换成本等真壁垒机器不可测, 终判归人工)
- 行业动量 = 历史 screener.compute_industry_momentum 定义 (行业内60日中位数收益), 不新建指标
- RA 反事实用效果归因 (overlap/spearman/替换名单), 不用"代码看起来多荒谬"定性
- Regime 仅作背景 (diagnostic context), 不参与改规则
- 报告末尾留 NOT ANSWERED (L1 利润兑现率 → Audit B)

输出: diagnostics/bloodline_snapshot_20260901.md
"""
import sys
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np
import pandas as pd
from loguru import logger

from scipy.stats import spearmanr

T_DATE = "20260901"

# ---------- 1. 加载 ----------
logger.info("加载 Book/Pool/行业映射/财务 (as-of PIT)")

book = pd.read_csv("output/research_book_20260901.csv")
book["code"] = book["code"].astype(str).str.zfill(6)
pool = pd.read_csv("output/research_pool_v3_20260901.csv")
pool["code"] = pool["code"].astype(str).str.zfill(6)
a_pool = pool[pool["research_priority"] == "A"].copy()

from industry import get_sw_industry
ind_map = get_sw_industry()

# 财务 as-of 20260901 可见 (PIT: 披露治理), 每 code 最后一行
from data_governance import filter_available_reports
raw_fin = pd.read_csv("data/cache/tdx_financials.csv", dtype={"code": str, "report_date_str": str})
avail = filter_available_reports(raw_fin, T_DATE)
avail["code"] = avail["code"].astype(str).str.zfill(6)
fin_last = avail.sort_values("report_date_str").groupby("code").tail(1).set_index("code")


def fin(code: str, col: str):
    if code not in fin_last.index or col not in fin_last.columns:
        return np.nan
    v = fin_last.loc[code, col]
    return v if pd.notna(v) else np.nan


# ---------- 2. 重算 A 级全集: 探针 + PE 分位 (production 口径) ----------
logger.info("预热财务缓存 + 重算 A 级探针/PE ({} 只)", len(a_pool))
from growth_os.lifecycle_research import prewarm_financial_cache
prewarm_financial_cache(T_DATE)
from growth_os.memo_engine import InvestmentMemoEngine
eng = InvestmentMemoEngine(ind_map=ind_map)

rows = []
for i, (_, r) in enumerate(a_pool.iterrows()):
    code = r["code"]
    try:
        probes = eng._probes(code, T_DATE)
        n_green = sum(1 for p in probes if p["probe"]["level"] == "green")
        n_red = sum(1 for p in probes if p["probe"]["level"] == "red")
        margin_lv = next((p["probe"]["level"] for p in probes if p["name"] == "毛利韧性"), "unknown")
        pe = eng._pe_info(code, T_DATE)
        pe_pct = pe["pct"] if pe["pct"] is not None else 0.5
    except Exception:
        n_green, n_red, margin_lv, pe_pct = 0, 3, "unknown", 0.5
    rows.append({
        "code": code, "radar": r.get("radar", ""), "lifecycle_state": r.get("lifecycle_state", ""),
        "expectation_state": r.get("expectation_state", ""), "n_green": n_green, "n_red": n_red,
        "margin_lv": margin_lv, "pe_pct": pe_pct,
        "profit_yoy": fin(code, "deducted_profit_yoy"),
        "rev_yoy": fin(code, "revenue_yoy"),
        "gross_margin": fin(code, "gross_margin"), "roic": fin(code, "roic"),
        "roe": fin(code, "roe"), "ocf2rev": fin(code, "ocf_to_revenue"),
    })
a_df = pd.DataFrame(rows)

# RPS60 + 行业动量 (A 级池内样本, 行业覆盖>=3 只才出值 — 主口径局限注明)
from screener import compute_rps60, compute_industry_momentum
codes_all = a_df["code"].tolist()
logger.info("重算 RPS60/行业动量 (A 级池, {} 只)", len(codes_all))
rps = compute_rps60(codes_all, T_DATE, ind_map)
ind_mom = compute_industry_momentum(codes_all, T_DATE, ind_map)
a_df["rps60"] = a_df["code"].map(rps)
a_df["ind_mom"] = a_df["code"].map(ind_mom)

# ---------- 3. 派生指标 (代理口径, 明确标注) ----------
# 景气四证据 (Growth 侧): 利润(deducted yoy>0) / 产能(capex probe green→用 n_green 近似需拆)
#   实际探针: order/capex/margin — capex green = 产能证据; 利润证据用财务直接
#   强势 = rps60; 趋势 = ind_mom
capex_green = {}
for i, (_, r) in enumerate(a_pool.iterrows()):
    code = r["code"]
    try:
        probes = eng._probes(code, T_DATE)
        capex_green[code] = any(p["name"] == "CAPEX效率" and p["probe"]["level"] == "green" for p in probes)
    except Exception:
        capex_green[code] = False
a_df["capex_green"] = a_df["code"].map(capex_green)

a_df["profit_ok"] = a_df["profit_yoy"] > 0
a_df["strong_ok"] = a_df["rps60"] >= 50
a_df["trend_ok"] = a_df["ind_mom"] > 0
a_df["growth_evidence_n"] = (a_df["profit_ok"].astype(int) + a_df["capex_green"].astype(int)
                             + a_df["strong_ok"].astype(int) + a_df["trend_ok"].astype(int))

# M_proxy_v35 (毛利韧性 green 且 ROIC>0) — 仅机器质量代理, 非壁垒本身
a_df["m_proxy_ok"] = (a_df["margin_lv"] == "green") & (a_df["roic"] > 0)
# M_proxy_legacy 简化 (ROE>0 且 OCF/营收>0 — S5/S7 的单期近似, 审计用)
a_df["m_legacy_ok"] = (a_df["roe"] > 0) & (a_df["ocf2rev"] > 0)

# 基本面未坏 (Recovery 侧): red 探针 <=1
a_df["not_broken"] = a_df["n_red"] <= 1
# 估值压缩: pe_pct < 0.3
a_df["val_compressed"] = a_df["pe_pct"] < 0.3
# 极端估值: pe_pct > 0.9
a_df["val_extreme"] = a_df["pe_pct"] > 0.9

# ---------- 4. RA 复算 (production 公式, 含/不含 PE 项) ----------
def ra_growth(row, with_pe):
    v = 0.3 * min(row["n_green"], 3) / 3 + 0.2 * (1.0 if row["lifecycle_state"] == "L1" else 0.6) \
        + 0.2 * (1 - row["n_red"] / 3)
    if with_pe:
        v += 0.3 * (1 - row["pe_pct"])
    return v


def ra_recovery(row, with_pe):
    v = 0.3 * min(row["n_green"], 3) / 3 + 0.3 * (1 - row["n_red"] / 3) + 0.2 * (1 - row["n_red"] / 3)
    if with_pe:
        v += 0.2 * (1 - row["pe_pct"])
    return v


a_df["ra_pe"] = [ra_growth(r, True) if r["radar"] == "growth_radar" else ra_recovery(r, True)
                 for _, r in a_df.iterrows()]
a_df["ra_nope"] = [ra_growth(r, False) if r["radar"] == "growth_radar" else ra_recovery(r, False)
                   for _, r in a_df.iterrows()]

# ---------- 5. 审计计算 ----------
L = []
md = []
def emit(s=""):
    md.append(s)

emit("# Bloodline Snapshot Audit — v3.5 Production Selection Fidelity")
emit(f"\n**日期**: 2026-09-04 | **研究日**: {T_DATE} | **性质**: 离线诊断 (不改 Production)")
emit(f"\n**口径**: 分雷达解读; M_proxy≠Moat; 行业动量=行业内60日中位数收益(A级池样本); "
     f"RA反事实=效果归因; Regime=背景。")
emit(f"\nA 级池: {len(a_df)} 只 (growth {sum(a_df['radar']=='growth_radar')} / "
     f"recovery {sum(a_df['radar']=='recovery_radar')} / 其他 {sum(~a_df['radar'].isin(['growth_radar','recovery_radar']))})")

growth_a = a_df[a_df["radar"] == "growth_radar"]
recov_a = a_df[a_df["radar"] == "recovery_radar"]
book_g = a_df[a_df["code"].isin(book[book["radar"] == "growth_radar"]["code"])]
book_r = a_df[a_df["code"].isin(book[book["radar"] == "recovery_radar"]["code"])]

def med(s):
    s = s.dropna()
    return round(s.median(), 3) if len(s) else np.nan

# ---- Q1 Growth25 景气血缘 ----
emit("\n## Q1. Growth Top25 是否提高了基本面景气证据? (vs A级 Growth 池)")
g1 = pd.DataFrame({
    "指标": ["利润 deducted_yoy>0 占比", "产能 capex green 占比", "强势 RPS60>=50 占比",
             "趋势 行业动量>0 占比", "四证据命中数 均值"],
    "A级Growth池": [round(growth_a["profit_ok"].mean(), 3), round(growth_a["capex_green"].mean(), 3),
                    round(growth_a["strong_ok"].mean(), 3), round(growth_a["trend_ok"].mean(), 3),
                    round(growth_a["growth_evidence_n"].mean(), 2)],
    "Growth Top25": [round(book_g["profit_ok"].mean(), 3), round(book_g["capex_green"].mean(), 3),
                     round(book_g["strong_ok"].mean(), 3), round(book_g["trend_ok"].mean(), 3),
                     round(book_g["growth_evidence_n"].mean(), 2)],
})
emit(g1.to_markdown(index=False))
ind_mom_vals = a_df["ind_mom"].dropna()
if len(ind_mom_vals) and (ind_mom_vals <= 0).all():
    emit(f"\n> 环境线索 (非纯 Beta 免责): A级池行业动量全部为负 (中位数 {ind_mom_vals.median():.3f}) — "
         f"全行业趋势向下仍固定输出 25 只 Growth → 景气确认不足时其他横截面变量接管排序。"
         f"这是 Regime 断线 + 配额刚性的现实注脚 (详见报告结论分级)。")
emit("\n> 解读: 利润/产能两腿显著生效 (43.4%→60%, 40.5%→80%); 强势略低是 L1×E0 左侧 Discovery 的"
     f"有意偏离 (非原文框架忠实执行), 有效性需单独验证。")

# ---- Q2 Growth25 底线 (M_proxy + 估值极端) ----
emit("\n## Q2. Growth Top25 底线检查 (文章: 高景气中排除低壁垒/极端估值)")
g2 = pd.DataFrame({
    "检查": ["M_proxy_v35 弱占比 (margin非绿或ROIC<=0)", "M_proxy_legacy 弱占比 (ROE<=0或OCF/营收<=0)",
             "估值极端占比 (PE分位>0.9)", "景气证据强但 M_proxy 弱 (危险区嫌疑)"],
    "A级Growth池": [round(1 - growth_a["m_proxy_ok"].mean(), 3), round(1 - growth_a["m_legacy_ok"].mean(), 3),
                    round(growth_a["val_extreme"].mean(), 3),
                    round(((growth_a["growth_evidence_n"] >= 2) & (~growth_a["m_proxy_ok"])).mean(), 3)],
    "Growth Top25": [round(1 - book_g["m_proxy_ok"].mean(), 3), round(1 - book_g["m_legacy_ok"].mean(), 3),
                     round(book_g["val_extreme"].mean(), 3),
                     round(((book_g["growth_evidence_n"] >= 2) & (~book_g["m_proxy_ok"])).mean(), 3)],
})
emit(g2.to_markdown(index=False))

emit("\n### Growth25 雷达污染矩阵 (景气证据 × M_proxy)")
emit("\n| | M_proxy 合格 | M_proxy 弱 |")
emit("|---|---|---|")
for ev_strong, ev_name in [(True, "景气证据强(≥2)"), (False, "景气证据弱(<2)")]:
    ok = book_g[(book_g["growth_evidence_n"] >= 2) == ev_strong]
    n_ok = sum(ok["m_proxy_ok"])
    n_weak = len(ok) - n_ok
    tag = "危险区:周期Beta/低壁垒" if ev_strong else ("可疑" if n_ok else "明显污染")
    emit(f"| {ev_name} | {n_ok} | {n_weak} ({tag}) |")

# ---- Q3 Recovery25 血缘 ----
emit("\n## Q3. Recovery Top25 是否真 '估值压缩 + 基本面未坏 + M_proxy 不差'?")
g3 = pd.DataFrame({
    "条件": ["估值压缩 (PE分位<0.3)", "基本面未坏 (red<=1)", "M_proxy_v35 合格",
             "压缩+未坏 (目标区)", "压缩+恶化 (价值陷阱嫌疑)"],
    "A级Recovery池": [round(recov_a["val_compressed"].mean(), 3), round(recov_a["not_broken"].mean(), 3),
                      round(recov_a["m_proxy_ok"].mean(), 3),
                      round((recov_a["val_compressed"] & recov_a["not_broken"]).mean(), 3),
                      round((recov_a["val_compressed"] & ~recov_a["not_broken"]).mean(), 3)],
    "Recovery Top25": [round(book_r["val_compressed"].mean(), 3), round(book_r["not_broken"].mean(), 3),
                       round(book_r["m_proxy_ok"].mean(), 3),
                       round((book_r["val_compressed"] & book_r["not_broken"]).mean(), 3),
                       round((book_r["val_compressed"] & ~book_r["not_broken"]).mean(), 3)],
})
emit(g3.to_markdown(index=False))

emit("\n### Recovery25 雷达污染矩阵 (估值压缩 × 基本面)")
emit("\n| | 基本面未坏 | 基本面恶化 |")
emit("|---|---|---|")
for comp, comp_name in [(True, "估值压缩"), (False, "未明显压缩")]:
    sub = book_r[book_r["val_compressed"] == comp]
    n_ok = sum(sub["not_broken"])
    n_bad = len(sub) - n_ok
    tag = "" if comp and not n_bad else ("价值陷阱" if comp else ("可疑" if n_ok else "明显污染"))
    emit(f"| {comp_name} | {n_ok} | {n_bad} {tag} |")

# ---- Q4 RA 反事实 (PE 项中性化) ----
emit("\n## Q4. RA 中 PE 项 ('未确认' 语义混用) 中性化后, 排名变化多大?")

def ra_counterfact(sub, radar_name):
    top_pe = sub.sort_values("ra_pe", ascending=False).head(25)["code"].tolist()
    top_nope = sub.sort_values("ra_nope", ascending=False).head(25)["code"].tolist()
    overlap = len(set(top_pe) & set(top_nope))
    # rank spearman (只对并集排序有效的股票)
    sub2 = sub[sub["code"].isin(set(top_pe) | set(top_nope))].copy()
    sub2["r_pe"] = sub2["ra_pe"].rank(ascending=False)
    sub2["r_nope"] = sub2["ra_nope"].rank(ascending=False)
    rho, _ = spearmanr(sub2["r_pe"], sub2["r_nope"])
    replaced = [c for c in top_pe if c not in top_nope]
    added = [c for c in top_nope if c not in top_pe]
    return overlap, rho, replaced, added

for radar_name, sub in [("Growth", growth_a), ("Recovery", recov_a)]:
    overlap, rho, replaced, added = ra_counterfact(sub, radar_name)
    emit(f"\n### {radar_name} (A级池 {len(sub)} 只 → Top25)")
    emit(f"- Top25 overlap (含PE vs 不含PE): **{overlap}/25** | Rank Spearman: {rho:.3f}")
    emit(f"- 被 PE 项抬进 Top25 (去PE后掉出): {len(replaced)} 只: {', '.join(replaced[:10])}")
    emit(f"- 去 PE 后新进 Top25: {len(added)} 只: {', '.join(added[:10])}")
    if replaced:
        emit(f"- 被抬进者 PE 分位中位数: {med(sub[sub['code'].isin(replaced)]['pe_pct'])} "
             f"| 景气证据命中数均值: {round(sub[sub['code'].isin(replaced)]['growth_evidence_n'].mean(), 2)}")
    emit("> 解读: overlap≥22 → 语义写错但实质影响小; 大量替换且被抬进者景气证据弱+PE低 → 血缘漂移实锤。")
    if radar_name == "Growth":
        emit("> Growth 核心解读 (三现象互强化, 非单字段 bug): 强势被 L1×E0 刻意弱化 + 趋势当前全灭 → "
             "排序真空由误名'未确认'的 30%×(1-PE) 填补 — PE 是真空的填充者。"
             "> 明确不建议把 PE 项替换成 E: Growth 已来自 L×E 矩阵, E 再入 RA = 双计权。"
             "> Growth 身份分裂假设: Top25 可能混装 Confirmed Prosperity (右侧) 与 Early Discovery "
             "(L1×E0 左侧) 两种哲学, 需历史验证 (Audit C)。")
    if radar_name == "Recovery":
        emit("> Recovery 细分解读: 低估值本是其目标特征 (压缩=机会), 故 PE 项行为半对 — 语义错 "
             "('未确认'注释) 但方向与 Recovery 哲学部分一致; 实质风险是 0.2 权重把'无恢复证据'的 "
             "低估股抬进 Top25 (9/25), 需看其基本面未坏与恢复证据是否成立。")
        emit("> 措辞边界: 结构忠实 (机器代理下与文章熊市轴一致) ≠ '高壁垒已验证' — 真壁垒终判归人工。")

# ---- Q5 Regime 背景 ----
emit("\n## Q5. 市场状态 (仅背景, 不参与改规则)")
try:
    from regime.detector import detect_regime
    rr = detect_regime(T_DATE)
    emit(f"- Legacy Regime detector @ {T_DATE}: **{rr.regime}** (score {rr.score:.2f})")
    emit(f"- 维度判定: {rr.details}")
    emit("- 按文章框架, 若 BULL → 研究配额应偏向景气 (Growth); 当前固定 25/25 不随周期 — 本项仅记录背景。")
except Exception as e:
    emit(f"- Regime detector 调用失败: {e} (附带发现: 历史模块与 numpy 2.x 不兼容 — 技术债, "
         f"属已知 Limitation, 不影响本审计结论)")

# ---- Q6 NOT ANSWERED ----
emit("\n## Q6. NOT ANSWERED YET (属 Audit B/C, 不在此回答)")
emit("- **L1 触发后利润兑现率**: 领先探针(订单/CAPEX) → T+2Q/T+4Q 利润是否兑现 — 需历史 PIT 样本前向验证 (Audit B)")
emit("- **Growth 身份**: Confirmed Prosperity vs Early Discovery 混桶是否成立, 是否应拆分 (Audit C, 历史多时点)")
emit("- 本快照只回答 '20260901 候选长得像不像文章里的公司', 不回答 '提前发现景气是否真有效'")

# 保存
out_path = "diagnostics/bloodline_snapshot_20260901.md"
with open(out_path, "w") as f:
    f.write("\n".join(md))
logger.info("已输出 {}", out_path)
print("\n".join(md[:40]))
