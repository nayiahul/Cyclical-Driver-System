# B_PROXY FIELD MAPPING — Audit C Implementation Gate 0 结论文档

**状态**: ✅ CLOSED (2026-09-04) — 字段血缘 + coverage probe + 交易日全部钉死
**日期**: 2026-09-04 | **依据**: 源码勘察 (signals.py / screener.py / growth_probes.py / bloodline_snapshot_audit.py) + Audit C Design v0.2 §4.4/§4.5

---

## 核心结论（防语义偷换, 写码前必须遵守）

> Gate 0 源码勘察发现: **Production 中不存在正式 B_proxy_v35**; `probe_capex_efficiency` 与 F-Capacity 共享 CAPEX 输入, 不具备独立 Barrier 代理资格。Audit C 主 v35 分层应沿用 Bloodline Snapshot Audit 已实际使用的 `margin_resilience=green AND ROIC>0`; legacy S5/S7 作为血缘敏感性层; **二者均仅为质量/壁垒弱代理, 不得升级为真实 moat verdict**。
> 禁止的链条: CAPEX效率 → 质量 → 壁垒 → 硬Gate（源码事实下站不住）。

---

## 1. Legacy B_proxy（S5/S7）— 数据源非 TDX

| 项 | 事实 | 源码证据 |
|---|---|---|
| 数据源 | **AKShare** `stock_financial_analysis_indicator` → `data/cache/financial_data.csv`（非 TDX） | signals.py L26 `FIN_CACHE = "data/cache/financial_data.csv"` |
| S5 盈利稳定性 | 字段 `加权净资产收益率(%)` → `roe_weighted`; 规则: ≥`ROE_MIN_QUARTERS` 期 → tail(12).std() → **行业内反向 Z** | signals.py L278-296 |
| S7 现金流质量 | 字段 `经营现金净流量对销售收入比率(%)` → `ocf_to_revenue`; 规则: 最新一期 **仅 >0 保留** → 行业内 Z | signals.py L299-321 |
| S7 盲区 | 负 OCF/Revenue → **NaN 而非低分**（弱质量识别天然盲区） | signals.py L312-315 |
| moat 组合 | `moat = mean([S5, S7])` 可用项均值; **两者皆缺 → 0.0**（Audit C 禁止沿用此缺失补 0） | screener.py L314-315 |
| moat 分级 | `pd.cut(moat, [-99,-0.3,0.3,99])` → 低/中/高; 弱 = moat < -0.3 | screener.py L622 |
| 行业依赖 | S5/S7 均做行业内 Z → **继承 Industry PIT 债**（2026-05 静态快照倒灌） | signals.py L296/L319 |
| 历史覆盖 | financial_data.csv 自 2012-03; 2022 实测 S5 65.1% / S7 57.2% → 4 Pilot 时点预期 **PARTIAL** | 项目 inventory |

**Audit C 映射**（不发明阈值, 修正缺失补 0 行为）:
```text
B_LEGACY_WEAK    = moat < -0.3
B_LEGACY_OK      = moat >= -0.3
B_LEGACY_UNKNOWN = S5 且 S7 均缺失（不再补 0）
元数据: b_legacy_coverage = 0/1/2（诊断用）
```

## 2. B_proxy_v35 — Production 无正式定义; 采用 Bloodline Audit 血缘

| 项 | 事实 | 源码证据 |
|---|---|---|
| Production 现状 | 无任何 `B_proxy` 组合定义（order/capex/margin 三探针并列, 无壁垒概念） | growth_probes.py |
| Margin Resilience | TDX `gross_margin`(col202) + `revenue_yoy`(col183); 需 ≥8 期; green 两路径: ① gm_recent>35 & gm_trend>0 & rev_yoy>20 ② gm_recent>30 & \|gm_trend\|<2; red: gm_trend<-3 或 gm_std>8 | growth_probes.py L113-132 |
| margin 掺景气 | green 路径①直接要求 rev_yoy>20 → **margin 非纯壁垒代理** | growth_probes.py L120 |
| CAPEX Efficiency | TDX `capex_cash`(col114) + `roic`(col329); green: CAPEX>+30% & ROIC↑ 或 ROIC↑ | growth_probes.py probe_capex_efficiency |
| **capex 探针资格** | **与 F-Capacity 共享 capex_cash → 机械重复, 禁止作主 B_proxy**（仅可作 sensitivity/context） | §4.5 |

**Audit C 主分层**（沿用 bloodline_snapshot_audit.py 已落地定义）:
```text
B_V35_OK      = margin_resilience == green AND ROIC > 0
B_V35_WEAK    = margin_resilience == red OR ROIC <= 0
B_V35_UNKNOWN = margin unknown OR ROIC missing
```
Bloodline Audit 原实现用布尔（unknown 落 False）→ **Audit C 必须修正为三态**, 禁止 unknown→weak。

**⚠️ 决策点（G0-A 后确认）**: margin **yellow** 态（明确数据, 非 unknown）在用户三态中无归属。提案: yellow+ROIC>0 单列观察层, 不计入 OK/WEAK 裁决组（防伪精确; 与 Audit C 分层精神一致）; 待 G0-A 覆盖率数据后冻结。

## 3. F ↔ B_proxy 输入重叠矩阵（§4.5 必录）

| 组合 | 共享输入 | 重叠级 |
|---|---|---|
| F-Profit(S1) ↔ B_v35(Margin) | revenue_yoy | LOW/PARTIAL（注明即可） |
| F-Profit(S1) ↔ S7 | OCF | PARTIAL |
| F-Capacity(S2) ↔ S5 | ROE 概念 | PARTIAL |
| **F-Capacity(S2) ↔ capex 探针** | **capex_cash 直接重复** | **HIGH — capex 探针降级为 context** |
| F-Capacity ↔ B_v35(Margin) | 无 | 无 |

**结论**: 不存在完全与 F 正交的机器壁垒代理 → B_proxy 只能做**条件分层/增量诊断**, 不能证明机器测出 moat; 真壁垒终判归人工（Audit C Design §4.3）。

## 4. 历史可用性预期

| 数据 | 覆盖 | 4 Pilot 时点预期 |
|---|---|---|
| Legacy (financial_data.csv) | 2012-03 起; 2022 实测 S5 65.1%/S7 57.2% | PARTIAL（股票级缺失 + S7 负值转 NaN） |
| v35 (TDX) | 1989-12~2026-06, 5213 只 | EXPECTED PARTIAL（margin 需 8 期; 新股缺; ROIC 缺值）→ G0-A 实测钉死 |

## 5. Gate 状态 — 已关闭（G0-A/G0-B 完成, 2026-09-04）

### G0-B 交易日确认（实测 trade_calendar）

```text
2023-05-10 → 20230510 (交易日)
2023-11-10 → 20231110 (交易日)
2024-09-10 → 20240910 (交易日)
2025-05-10 → 20250512 (周六 → 顺延下一交易日)
```

### G0-A 覆盖率实测（diagnostics/b_proxy_coverage_probe.py, TDX 5213 只全量）

| t0 | universe | B_v35 OK | WEAK | YELLOW | UNKNOWN | B_legacy OK | UNKNOWN |
|---|---|---|---|---|---|---|---|
| 20230510 | 5213 | 20.4% | 34.7% | 38.0% | 6.9% | 63.6% | 36.4% |
| 20231110 | 5213 | 22.1% | 31.3% | 42.3% | 4.3% | 63.6% | 36.4% |
| 20240910 | 5213 | 23.6% | 27.7% | 45.8% | 3.0% | 63.6% | 36.4% |
| 20250512 | 5213 | 22.7% | 30.3% | 45.2% | 1.8% | 63.6% | 36.4% |

**关键读数**:
- B_v35: OK ~20-24%, **YELLOW 是大头 (38-46%)** → yellow 观察层方案必须冻结（已按四态实现）; UNKNOWN 低 (2-7%, 主要为新股/数据不足) — **覆盖率 PASS**
- B_legacy: OK 63.6% / **UNKNOWN 36.4% 恒定** — 原因是 financial_data.csv 仅覆盖 3406/5213 只 (65%), 与 inventory 2022 实测一致 → **覆盖率 PARTIAL**（恒定的表外缺失, 非时间不足）
- legacy WEAK=0 实证了 S7 负值→NaN 盲区（field mapping §1）: 负 OCF 公司不会成为 legacy weak, 而是进 UNKNOWN 或 OK
- 4 时点 v35 分布稳定 → 无时点异常

### yellow 决策点冻结

margin yellow + ROIC>0 → **单列观察层**（不计入 OK/WEAK 裁决组）; 已按四态实现于 probe。Audit C 主分析用 OK vs WEAK, yellow 分布另报。

### Gate 0 最终状态: ✅ CLOSED

Field mapping 冻结; 可进入 C-Pilot 实现（Commit 2）。

---
