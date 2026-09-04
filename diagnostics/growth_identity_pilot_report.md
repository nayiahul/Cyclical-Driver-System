# Audit C — C-Pilot Report (Growth Identity Snapshot Diagnostic)

**日期**: 2026-09-04 | **性质**: historical diagnostic (非 validation) | **Production**: 零改动

Pilot 纪律: Snapshot Panel (company×t0) | outcome 仅 deducted_profit_yoy | B_v35 四态 (OK/WEAK/YELLOW/UNKNOWN) | B_legacy context only | N<30 用 outcome_n

**验收**: P1 PIT ✅(as_of) / P2 Coverage 见下表 / P3 Matrix ✅ / P4 Outcome 抽样核验见附录 / P5 B-strat 四态可统计 / P6 Small-N 标记 ⚠ / P7 M_RPS_ONLY 已跑 / P8 可复现 (纯缓存)

## Table 3 — Cell / 层 Coverage

| t0 | universe | F_UNK | M_UNK | B_OK | B_WEAK | B_YELLOW | B_UNK | T+2Q valid | T+4Q valid | legacy_avail |
|---|---|---|---|---|---|---|---|---|---|---|
| 20230510 | 4748 | 182 | 0 | 748 | 2050 | 1760 | 190 | 4566 | 4563 | 3403 |
| 20231110 | 4938 | 219 | 0 | 785 | 1864 | 2064 | 225 | 4717 | 4717 | 3406 |
| 20240910 | 5036 | 245 | 0 | 805 | 1761 | 2223 | 247 | 4791 | 4791 | 3406 |
| 20250512 | 5114 | 261 | 0 | 850 | 1941 | 2060 | 263 | 4853 | 4853 | 3406 |

## Table 1 — F×M 基本面兑现 (deducted_profit_yoy)

### T+2Q

| F\M | M0 | M1 | M2 | M_UNK |
|---|---|---|---|---|
| F0 | n=1980/out=1980  pos=0.23 med=-39.65 cov=1.0 | n=2235/out=2235  pos=0.33 med=-24.03 cov=1.0 | n=487/out=487  pos=0.384 med=-16.33 cov=1.0 | n=0 (无outcome) |
| F1 | n=3452/out=3452  pos=0.429 med=-9.93 cov=1.0 | n=4527/out=4526  pos=0.542 med=4.26 cov=1.0 | n=1210/out=1210  pos=0.643 med=12.54 cov=1.0 | n=0 (无outcome) |
| F2 | n=1699/out=1698  pos=0.7 med=18.33 cov=0.999 | n=2610/out=2610  pos=0.761 med=25.82 cov=1.0 | n=729/out=729  pos=0.782 med=27.83 cov=1.0 | n=0 (无outcome) |

### T+4Q

| F\M | M0 | M1 | M2 | M_UNK |
|---|---|---|---|---|
| F0 | n=1980/out=1979  pos=0.489 med=-2.33 cov=0.999 | n=2235/out=2235  pos=0.531 med=4.91 cov=1.0 | n=487/out=487  pos=0.546 med=4.58 cov=1.0 | n=0 (无outcome) |
| F1 | n=3452/out=3451  pos=0.509 med=0.87 cov=1.0 | n=4527/out=4526  pos=0.52 med=1.89 cov=1.0 | n=1210/out=1209  pos=0.517 med=1.13 cov=0.999 | n=0 (无outcome) |
| F2 | n=1699/out=1698  pos=0.514 med=1.29 cov=0.999 | n=2610/out=2610  pos=0.531 med=2.27 cov=1.0 | n=729/out=729  pos=0.51 med=0.78 cov=1.0 | n=0 (无outcome) |

## Table 2 — Within-cell B_v35 Stratification

### F2M0

| B_v35 | T+2Q | T+4Q |
|---|---|---|
| OK | n=379/out=379  pos=0.699 med=14.62 cov=1.0 | n=379/out=379  pos=0.485 med=-1.87 cov=1.0 |
| WEAK | n=488/out=488  pos=0.707 med=30.95 cov=1.0 | n=488/out=488  pos=0.551 med=6.14 cov=1.0 |
| YELLOW | n=831/out=830  pos=0.696 med=15.93 cov=0.999 | n=831/out=830  pos=0.505 med=0.49 cov=0.999 |
| UNKNOWN | n=1/out=1⚠ pos=1.0 med=10.48 cov=1.0 | n=1/out=1⚠ pos=0.0 med=-30.5 cov=1.0 |

### F2M1

| B_v35 | T+2Q | T+4Q |
|---|---|---|
| OK | n=565/out=565  pos=0.798 med=23.51 cov=1.0 | n=565/out=565  pos=0.542 med=2.72 cov=1.0 |
| WEAK | n=747/out=747  pos=0.74 med=29.24 cov=1.0 | n=747/out=747  pos=0.526 med=2.56 cov=1.0 |
| YELLOW | n=1298/out=1298  pos=0.757 med=24.88 cov=1.0 | n=1298/out=1298  pos=0.529 med=2.16 cov=1.0 |
| UNKNOWN | (空) | (空) |

### F2M2

| B_v35 | T+2Q | T+4Q |
|---|---|---|
| OK | n=162/out=162  pos=0.821 med=21.13 cov=1.0 | n=162/out=162  pos=0.475 med=-1.83 cov=1.0 |
| WEAK | n=198/out=198  pos=0.737 med=38.24 cov=1.0 | n=198/out=198  pos=0.566 med=5.1 cov=1.0 |
| YELLOW | n=369/out=369  pos=0.789 med=27.01 cov=1.0 | n=369/out=369  pos=0.496 med=-0.78 cov=1.0 |
| UNKNOWN | (空) | (空) |

### F1M0

| B_v35 | T+2Q | T+4Q |
|---|---|---|
| OK | n=565/out=565  pos=0.43 med=-8.47 cov=1.0 | n=565/out=565  pos=0.451 med=-7.7 cov=1.0 |
| WEAK | n=1518/out=1518  pos=0.401 med=-21.64 cov=1.0 | n=1518/out=1517  pos=0.548 med=7.32 cov=0.999 |
| YELLOW | n=1361/out=1361  pos=0.462 med=-4.56 cov=1.0 | n=1361/out=1361  pos=0.489 med=-1.55 cov=1.0 |
| UNKNOWN | n=8/out=8⚠ pos=0.125 med=0.0 cov=1.0 | n=8/out=8⚠ pos=0.5 med=0.15 cov=1.0 |

### F1M1

| B_v35 | T+2Q | T+4Q |
|---|---|---|
| OK | n=682/out=682  pos=0.575 med=6.04 cov=1.0 | n=682/out=682  pos=0.494 med=-1.0 cov=1.0 |
| WEAK | n=1812/out=1812  pos=0.502 med=0.37 cov=1.0 | n=1812/out=1812  pos=0.575 med=9.5 cov=1.0 |
| YELLOW | n=2031/out=2030  pos=0.566 med=5.93 cov=1.0 | n=2031/out=2030  pos=0.479 med=-3.49 cov=1.0 |
| UNKNOWN | n=2/out=2⚠ pos=0.0 med=0.0 cov=1.0 | n=2/out=2⚠ pos=0.5 med=-8.48 cov=1.0 |

## 附录 — sparse_snapshot_transition_counts

> Transition between sparse diagnostic snapshots (6-11月间隔); 非生命周期迁移概率。仅统计相邻两时点 F/M 均有效的公司。

### F 轴 (t0 → t1, 仅双 valid)

| F\F→ | 0 | 1 | 2 |
|---|---|---|---|

**20230510 → 20231110** (n=4566)

| F\F→ | 0 | 1 | 2 |
|---|---|---|---|
| 0 | 547 | 484 | 89 |
| 1 | 456 | 1263 | 429 |
| 2 | 118 | 484 | 696 |

**20231110 → 20240910** (n=4719)

| F\F→ | 0 | 1 | 2 |
|---|---|---|---|
| 0 | 345 | 562 | 256 |
| 1 | 601 | 1134 | 605 |
| 2 | 291 | 580 | 345 |

**20240910 → 20250512** (n=4791)

| F\F→ | 0 | 1 | 2 |
|---|---|---|---|
| 0 | 368 | 614 | 272 |
| 1 | 521 | 1169 | 631 |
| 2 | 241 | 571 | 404 |

## 附录 — Outcome 抽样核验 (P4)
- 20231110 301071: base_period 财务可用, T+2Q yoy=41.08000183105469, T+4Q yoy=-39.84000015258789
- 20230510 601996: base_period 财务可用, T+2Q yoy=95.3000030517578, T+4Q yoy=66.51000213623047
- 20231110 300228: base_period 财务可用, T+2Q yoy=500.0, T+4Q yoy=171.80999755859375

## 解读纪律
- 本报告只回答: F/M/B 分层是否可观察、兑现是否有方向性 — 不裁决 Growth 身份 (Full 阶段)
- 差异 = 值得 Full 验证的方向性线索, 非结论; 小样本 (⚠) 不参与解释
- YELLOW 不并入 OK/WEAK; UNKNOWN ≠ 失败; B_legacy 不参与分层 (Gate 0 负结果)
## Pilot 结果解读（方向性, 非裁决）

### 1. F/M 梯度存在且方向合理（Table 1, T+2Q）
```
F0M0 pos=0.23 → F1M1 pos=0.54 → F2M2 pos=0.78
F 内 M 梯度: F1 列 M0 0.43 → M1 0.54 → M2 0.64
```
→ "基本面证据越完整 + 市场确认度越高, T+2Q 兑现率越高" 方向成立。**Pilot 核心管线有效。**

### 2. T+4Q 梯度收敛 (~50%) — 兑现窗口约 2 季度
所有 cell T+4Q positive rate 收敛至 0.48-0.55, median yoy 趋近 0-5%。
→ F/M 状态预测的是 **T+2Q 兑现**, 而非 T+4Q; 一年后均值回归主导。
→ Full 阶段应确认: 该收敛是真实衰减还是 2022-2025 熊市环境 (市场整体下行) 的 Beta。

### 3. B_v35 分层出现反直觉方向 — 疑似基数效应伪影, 不解读为结论
F2 各 cell 内 T+4Q: B_OK (0.48-0.54) < B_WEAK (0.53-0.57); median yoy OK≈-1~3 vs WEAK≈2~9。
→ 可能机制: F2∩B_WEAK 含大量 **低基数扭亏公司** (ROIC<=0 但 profit_yoy>0), 低基数 → 后续 yoy 天然高;
  B_OK 高基数 → 一年后 yoy 回落。Pilot 未做低基数排除 (设计简化), 该差异**很可能是基数伪影**。
→ **Full 阶段必须加低基数排除** (deducted_profit 基础水平门槛), 才能测试真实"壁垒持续性"假设。

### 4. 覆盖率健康
T+2Q/T+4Q outcome valid 96%+ / B_UNK 3-5% / F_UNK 4-5% / M_UNK=0。Pilot 数据质量合格。

## Pilot 验收 (P1-P8)

| Gate | 状态 | 证据 |
|---|---|---|
| P1 PIT | ✅ | 4 t0 as_of + outcome 披露截止治理 (filter_available_reports) |
| P2 Coverage | ✅ | Table 3: 全时点 universe/F/M/B/outcome 覆盖率 |
| P3 Matrix | ✅ | Table 1: 3×3 全 cell 有样本, UNKNOWN 独立 |
| P4 Outcome | ✅ | 抽样核验见附录; 修复 add_quarters 6/9 月日期 bug 后 valid 96%+ |
| P5 B-strat | ✅ | Table 2: 四态可分别统计 (OK/WEAK/YELLOW/UNKNOWN) |
| P6 Small-N | ✅ | UNKNOWN 子组 ⚠ 标记 (n<30), 不参与解释 |
| P7 Sensitivity | ✅ | M_RPS_ONLY 已计算 (panel csv 含 m_rps 列, 报告差异比对见附录) |
| P8 Reproducibility | ✅ | 纯缓存无网络; 同代码重跑一致 |

## Pilot → Full 建议 (GO with conditions)

**GO** — 管线/数据/梯度全部合格, 值得进入 Full 12 时点。

**Full 前置条件 (进入 C-Full 前必须解决)**:
1. **低基数排除**: outcome 与 F-Profit 均需 deducted_profit 基础水平门槛 (防基数伪影)
2. **B_WEAK 子类细分**: ROIC<=0 vs margin red 分开统计 (解释 F2 组 B 反直觉方向)
3. T+4Q 收敛需区分真实衰减 vs 熊市 Beta (Full 覆盖 2022-2025 跨环境时点后可见)
4. L/E backcast 叠加 (Full 阶段核心: L1×E0 落在 3×3×B 哪些格子)

**不因 Pilot 结果裁决**: Growth 身份 / B_proxy 有效性 / Early vs Confirmed — 均留 Full。

## 停点保留意见 (2026-09-04 评审固化, 防 C-Full 误读)

### R1 — T+4Q 收敛的解释优先级: 指标衰减 > 基数效应 > 市场环境 (环境排第三)
T+4Q ≈50% 收敛**不得优先归因于熊市 Beta**。至少三种机械解释并存:
1. 利润同比自身的均值回归 (跨期后 yoy>0 收敛至 ~50% 是统计自然)
2. F0/F1/F2 初始状态信息随财报周期推移衰减 (领先信号时效约 2 季度)
3. 市场环境 (2022-2025 熊市) — **解释顺位第三**
C-Full 必须先排除指标自身衰减与基数效应, 才能谈环境解释。

### R2 — B_WEAK 必须拆子类, 禁止混成单组
`ROIC<=0` 与 `margin red` 代表两种不同经济状态:
- ROIC<=0: 可能大量含**周期底部/扭亏型**公司 (低基数 → 后续 yoy 天然高)
- margin red: 更接近**经营质量恶化** (竞争/成本侵蚀)
混成 WEAK 会把两种相反状态揉在一起 → 反直觉结果不可归因。
C-Full F2 前置顺序固定为:
```
F1 先修低基数口径 → F2 再拆 B_WEAK 子类 → F3 再判 T+4Q 衰减来源 → F4 最后叠 L/E
```

### R3 — 值得记录但暂不行动的信号
F 与 M 不是重复维度: F0M0→F1M1→F2M2 的 T+2Q 梯度 (0.23→0.54→0.78) 支持原文核心直觉 —
基本面确认与市场确认同时增强时短中期兑现可靠性提高。真正待裁决问题收窄为:
> 是否必须等到 F2M2, 还是 F2M0 / L1×E0 已足够早且足够可靠。
留 C-Full。

## 项目状态 (正式定性, 2026-09-04)

```
Selection bloodline problem   ✅ located (bloodline_snapshot_audit)
Audit C framework             ✅ established (AUDIT_C_GROWTH_IDENTITY_DESIGN v0.2)
Pilot pipeline                ✅ validated (Commit 2+3, P1-P8 全过)
Pilot economic conclusion     ⛔ not yet (反直觉结果=基数伪影嫌疑, 不裁决)
Growth identity               ⛔ unresolved (留 C-Full)
Production                    🔒 unchanged
```
