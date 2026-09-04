# Audit C — Growth 身份历史诊断设计 v0.2（冻结候选）

**状态**: DESIGN BASELINE v0.2 — 设计原则冻结; Implementation blocked by **B_proxy Mapping Gate**（字段级映射未关闭, 见 §4.4）| **日期**: 2026-09-04 | **性质**: 冻结期离线诊断设计 — 不修改 Production
**上游**: Bloodline Snapshot Audit `8c4efb2` + C0 Data Eligibility 勘察 + v0.1 设计草案（消息层）+ 5 项修订
**血缘**: 本文件为 v0.1 的**完整落盘版**（v0.1 未落盘, 所有有效内容并入本版; 修订处以 ⚠️v0.2 标注）

**唯一业务目标（约束所有设计决策）**:
> 通过景气度、壁垒、估值，找到值得进一步研究的标的。

Audit C 是**手段**（裁决 Growth Radar 该找哪类候选、是否需要壁垒底线），不是目的；所有结论只映射为 Post-10-02 Candidate Action（§9），禁止直接修改 Production。

**最终研究问题（四问递进, v0.2 冻结）**:
1. 景气基本面证据越完整（F0→F2），未来兑现是否越可靠？
2. 左侧 Early 是否能稳定迁移为右侧 Confirmed（同一条生命周期？）？
3. 这种迁移与兑现是否依赖 B_proxy 合格？
4. 不同市场确认状态是否只是同一景气生命周期的不同阶段？

---

## 1. C0 数据资格与硬边界（v0.1 继承 + U1 新增）

### 1.1 数据资格表

| 数据层 | 状态 | Audit C 使用方式 |
|---|---|---|
| Financial PIT | PASS（可见性）+ revision caveat | 主裁判 |
| Price PIT | PASS | Market 轴及辅助结果 |
| Universe PIT | FAIL / U0 | 只能构造 Survivor-conditioned 样本 |
| Industry PIT | PARTIAL | 主版本保留, RPS-only 敏感性分析 |
| ⚠️v0.2 Historical ST | **UNKNOWN / U1（新增, 见 §1.4）** | 单列声明, 不预设方向 |

### 1.2 Financial PIT 边界（v0.1 继承）

`FinancialData.as_of()` / `quarterly_series()` 经披露日治理，保证 **report visibility PIT**；但 TDX 缓存无历史版本化 → **不保证 historical value revision PIT**。所有接近分类阈值的样本保留原始连续值及距阈值距离，不因可能存在修订而人为重分类。

### 1.3 Universe U0 — Survivorship Bias（v0.1 继承）

历史样本只能近似为 `2026 当前 master AND list_date <= t`，**必须命名为 "Survivor-conditioned Universe"**。所有比例的严格解释为"在截至 2026 仍存续、且研究时点已上市的公司中……"。已知偏差方向：退市/严重失败缺失 → 失败率低估、兑现率高估、Early→Confirmed 比例高估。**U0 不仅污染样本完备性，也污染基本面兑现裁判本身** → Audit C = historical diagnostic，禁止称 historical validation。

### 1.4 ⚠️v0.2 U1 — Historical ST State Unknown（新增）

U0 排除后来退市的严重失败样本，但**不能吸收 ST 偏差**：2023 年为 ST、2026 已恢复并仍存续的公司会混入样本，而 Audit C 无法识别其当时 ST 身份。

- 禁止用当前 ST 标签倒灌历史；不因无法恢复 ST 而自动剔除；单独声明 U1。
- **偏差方向不预设**（纳入当年问题公司 → 可能降低兑现表现; 严重失败退市者已被 U0 删除 → 又可能提高表现; 两力反向, 不能简单称"偏保守"）。

### 1.5 Model-version Backcast 边界（v0.1 继承）

2026 v3.5 规则回放 2022-2025 数据 = "如果今天这套规则面对当时数据会如何分类"，**不是**"当年系统实际如何决策"。禁止解释为历史策略绩效回测。

---

## 2. 时间窗口与研究时点（v0.1 继承）

### 2.1 窗口

2022-2025（价格 2021+ 足够前置窗口; 与 PDR 可复现窗口一致; T+2Q/T+4Q 留后验空间）。

### 2.2 t0 = 披露锚点，非机械季度末

```
05-10  (年报+Q1 披露完成)
09-10  (半年报披露完成)
11-10  (Q3 披露完成)
非交易日顺延下一交易日
2022-2025 × 3/年 ≈ 12 时点
特征严格: feature_timestamp <= t0
```

### 2.3 Outcome 窗口

T+2Q / T+4Q 两档; 只纳入截至 2026-09-04 已披露对应后验报告的样本; 晚近 snapshot 的 T+4Q 自动缺失（每个 horizon 单独报 N）; 禁止用未披露报告填补。

---

## 3. ⚠️v0.2 样本构造（v0.1 §2 继承 + Pilot 阶段化）

### 3.1 不重建历史 Growth Top25 / RA（v0.1 继承）

不运行历史 RA、不构造 Growth25、不用 PE 排名、不用 25/25 quota — 隔离裁决 Growth 身份，防 Bloodline Audit 已发现问题二次污染。

### 3.2 每 t0 基础样本（v0.1 继承）

```
Survivor-conditioned Universe → list_date<=t0 → PIT 财务可用 → PIT 价格可用
→ 计算 F/M/B_proxy
禁止因当前 ST 状态删除历史股票（U1 声明代替剔除）
```

### 3.3 Missing ≠ False（v0.1 继承）

任何缺失 → UNKNOWN，不得记 0/failed。每 snapshot 输出: universe_n / financial_available_n / price_available_n / industry_available_n / F_unknown_n / B_unknown_n。

### 3.4 Panel vs Episode（v0.1 继承）

Panel View（所有 company×snapshot, 描述用）+ Episode View（主裁判: 同公司连续处于同一 3×3×B cell 只计首次进入, 离开后再次进入才成新 episode）。

### 3.5 ⚠️v0.2 两阶段实施（修订新增）

**禁止第一版直接跑 12 snapshot × 全 universe × F/M/B × L/E × 全部 outcome。**

**Stage C-Pilot**（先行, 4 时点: **2023-05-10 / 2023-11-10 / 2024-09-10 / 2025-05-10**, 非交易日顺延）:
- 时点选择理由: 覆盖 05(年报+Q1) / 09(半年报) / 11(Q3) 三种披露信息状态 — Pilot 首要任务是验证管线在不同披露锚点都不出错, 而非统计代表性; 跨 2023-2025 不集中单一市场环境; 截至 2026-09-04 四时点 T+2Q 基本成熟、T+4Q 有足够后验; **2025-09 不入选 Pilot**（Pilot 的价值是暴露实现错误, Full 12 时点自然包含）
- 只运行: Universe approximation → F 轴 → M 轴 → B_proxy → 3×3×B 分层 → 财务 outcome
- **不跑全量 L/E 回算**; E 可用 RPS 等原始市场字段描述但**禁止称 "historical E state"**; L 不用代理伪造
- Pilot 目的 = 验证: PIT 管线稳定 / F-M 正交 / B_proxy 覆盖 / cell 有可观察样本 / outcome 正确关联 / episode 去重正确 / 基本面方向性梯度存在
- **Pilot 不能裁决 L1×E0 vs F2M2** — 那是 Full 阶段的事

**Pilot → Full Gate**（工程/诊断条件, 非"看起来赚钱"）:
```
G1 数据: PIT guard 无异常 / Unknown 比例可解释 / outcome 正确对齐
G2 分组: 3×3×B 非大量结构性空格 / episode 构造正确 / M_FULL 与 RPS_ONLY 可同时算
G3 方向: F0→F1→F2 无严重反常 (sanity check, 非要求漂亮单调)
   F0~52% F1~55% F2~58% → 可继续 Full
   F0 70% F1 42% F2 28%   → STOP, 先查数据/定义
G4 代理: B_proxy 覆盖可用 / F↔B_proxy 输入重叠已解释（见 §4.5）
```

**Stage C-Full**: 12 snapshot × survivor universe × F/M/B × L/E v3.5 backcast × 四层 outcome — 此阶段才正式回答四问。

---

## 4. 3×3 状态矩阵 + B_proxy 分层（v0.1 §3 + ⚠️v0.2 修订）

原则: F 与 M 两轴**不共享输入变量**, 不建任何加权总分。

### 4.1 F 轴（Fundamental = 0/1/2）

- F-Profit（利润兑现）: 复用历史既有定义（扣非利润增长 + 低基数排除 + 一次性收益排除）— **不新发明阈值**
- F-Capacity（产能准备）: 纯财务字段（CAPEX / 合同负债, 复用历史定义）
- F0/F1/F2 = 0/1/2 腿成立; 缺失 → F_UNKNOWN

### 4.2 M 轴（Market = 0/1/2）

- M-Strength: RPS60（历史"强势"定义）
- M-Trend: 行业趋势 — 主版本复用 `compute_industry_momentum()` 血缘定义（行业内 60 日中位数收益），**非** 8 指数; 行业映射 2026-05 静态快照倒灌 → 标注 Industry PIT caveat
- 敏感性: M_FULL vs M_RPS_ONLY 必须同时生成; 核心结果仅在 M_FULL 成立 → 结论降级

### 4.3 ⚠️v0.2 B_proxy 分层（修订新增 — 壁垒维回归）

**命名**: M 已代表 Market → 壁垒代理统一叫 **B_proxy（Barrier Proxy）**，禁止 M_proxy。

```text
B_proxy = 机器可观测的壁垒/质量弱代理, ≠ 真实商业壁垒
（品牌/转换成本/客户认证/Installed Base/网络效应/专利/规模经济/渠道控制 → 机器不可测, 终判归人工）
```

构造: 保留两套血缘代理, 不造综合"壁垒分":
```text
B_proxy_legacy = 历史 S5/S7 类
B_proxy_v35    = 当前 margin resilience / ROIC-CAPEX quality
输出仅离散标签: B_PROXY_OK / B_PROXY_WEAK / B_PROXY_UNKNOWN
禁止: Barrier Score=82 / Moat=HIGH 类输出
```

### 4.4 ⚠️v0.2.1 Implementation Gate 0 — B_proxy 字段映射（设计 commit 后, 写码前必须关闭）

`B_PROXY_OK/WEAK` 是核心分层变量 — 字段未映射前实验分组未完全定义, 禁止宣称 Frozen。
写 `growth_identity_audit.py` 前先做一次独立小勘察, 产出:

```text
B_PROXY FIELD MAPPING

legacy:
  S5 -> exact source / field / formula (ROE 稳定性)
  S7 -> exact source / field / formula (OCF 质量)

v35:
  margin_resilience -> exact inputs / thresholds
  roic_capex_quality -> exact inputs / thresholds

historical availability:
  2023-05 PASS / PARTIAL / FAIL
  2023-11 ...
  2024-09 ...
  2025-05 ...
```

勘察通过后, 以一个小 implementation note 固化 (B_proxy mapping + Pilot 实际交易日), 不再做 v0.3 架构设计。

### 4.5 ⚠️v0.2.1 输入重叠检查（防"代理变量语义重叠制造假壁垒结论"）

**风险**: 若 F-Capacity 用 CAPEX, B_proxy_v35 又用 ROIC/CAPEX → "F2×B_OK 兑现更强"可能只是变量机械重叠, 非壁垒代理增量信息。

- Audit C 报告必须记录: `Input overlap: F↔B_proxy_legacy / F↔B_proxy_v35`（共享字段清单）
- 若 v35 proxy 与 F 高度共享输入 → 只能作敏感性层, 不能成为"壁垒提供独立增量"的主要证据
- **增量价值检验**: 只比较**同一 F/M cell 内** B_OK vs B_WEAK（如 F2M0/B_OK vs F2M0/B_WEAK）—— 在景气证据和市场确认程度相同时, 壁垒代理有无增量价值; 禁止跨 cell 比较把相关性当壁垒作用

**矩阵**: 每个 F×M cell 按 B_proxy 分层（F2M0/B_OK, F2M0/B_WEAK, ..., F2M2/B_OK, F2M2/B_WEAK），每子组独立报告 N / T+2Q / T+4Q / 状态迁移 / 市场确认 / Failure / 收益辅助。

**新增核心问题**: Early 的兑现是否依赖 B_proxy 合格？重点比较 Early×B_OK vs Early×B_WEAK, Confirmed×B_OK vs Confirmed×B_WEAK。B_proxy 分层有区分力 → 只能得出"机器质量代理有候选筛选价值"，**不得得出"机器识别了真护城河"**。

---

## 5. Current Growth OS Overlay（v0.1 继承, Full 阶段执行）

3×3 矩阵不替代 L/E。Full 阶段每个 t0 用当前 v3.5 规则回算 L/E 状态，记录 L1×E0 / L1×E1 作为当前 Early Discovery cohort，回答"L1×E0/E1 实际落在 3×3×B 哪些格子"。**不预设 Early 与 Confirmed 是两个独立桶** — 主假设是 Early→Transition→Confirmed 生命周期，核心输出含 Early→Confirmed 迁移率与迁移时间。

---

## 6. 四层裁判（v0.1 继承, 禁止 composite score）

1. **基本面兑现**（主裁判, PIT Financial）: T+2Q/T+4Q 的 deducted_profit_yoy / revenue_yoy / gross_margin / ROIC — 中位数/分位/改善比例/恶化比例/delta; 不合成; 核心问题: F0/F1/F2 与 L1×E0 的未来财务兑现是否存在稳定梯度
2. **状态迁移**: Early cohort 的 T+2Q/T+4Q 去向（Fundamental Improved / Transition / Confirmed / Remained Early / Deteriorated-Failed / UNKNOWN）; 核心输出: Early→Confirmed rate / Early→Failed rate / median transition time

⚠️v0.2.1 **持续性 outcome（B_proxy 关键裁判）**: 壁垒可能不决定"景气能不能起来", 而决定"景气能不能持续" — B_proxy 分层的关键 outcome 不只有 T+2Q 兑现, 须特别关注:
- T+4Q 持续性（兑现后是否维持, 而非掉回）
- 毛利保持 / ROIC 保持（相对 t0 的持续性 delta）
- Early→Confirmed 后是否继续维持（F2M1/F2M2 后不退化）

可能出现的核心发现形态: F2M0/B_OK → 大量迁移 F2M1/F2M2 且持续; F2M0/B_WEAK → 利润也兑现但之后掉回 — 若成立, 说明"B_proxy 决定持续性而非启动", 与原文"壁垒始终重要但阶段性让位于景气"深度吻合。
3. **市场确认**: E 迁移 / RPS 改善 / 行业趋势转正 / M0→M1→M2; 区分"基本面兑现+市场确认 / 兑现+未确认 / 失败+曾确认" — 防把"股价涨"当"基本面正确"
4. **价格结果**（仅辅助）: T+90/T+180 forward return / 相对宽基 / 最大回撤 — 收益不是一级裁判

---

## 7. 预注册解释规则（v0.1 情形 A-D 继承 + ⚠️v0.2 动作映射）

| 情形 | 判定 | 结论 |
|---|---|---|
| A | Early T+2Q/T+4Q 兑现明显优于基准 + 稳定迁移 F2M1/F2M2 | Early Discovery 是有效前置景气状态; L1×E0 是有效提前而非背离 |
| B | Early 兑现不优于低确认组 + 失败率高 + 极少迁移 | Early Discovery NOT SUPPORTED; Growth 需靠近右侧确认 |
| C | Early 兑现有效, 但 F2M2 市场确认/价格更强 | 同一生命周期不同阶段 → 两阶段管理讨论资格 |
| D | 差异随市场环境显著变化 | Regime 是缺失 Router 的证据; Audit C 只记录不恢复 |

---

## 8. 已知偏差声明（报告首页+结论页重复, v0.1 + ⚠️v0.2）

```
U0 — Survivorship Bias: 2026-survivor-conditioned; 高估兑现/低估失败/高估迁移
U1 — Historical ST Unknown (v0.2 新增): 历史 ST 状态不可 PIT 恢复; 方向不预设
I0 — Industry Mapping Drift: 2026-05 快照倒灌; RPS-only 敏感性缓解, 不消除
F0 — Financial Revision Risk: visibility PIT 已治理; 数值修订未治理
M0 — Model-version Backcast: 2026 v3.5 规则回放历史; ≠ 当年实际决策
D0 — Repeated Company Observations: 主结论用 Episode view
```

---

## 9. ⚠️v0.2 结果 → 动作映射（修订新增 — 服务唯一业务目标）

Audit C 所有输出只映射为 Post-10-02 Candidate Action，禁止直接改 Production:

| Audit C 结果 | 允许提出的候选动作 |
|---|---|
| Early 兑现稳定 + B_proxy 分层差异弱 | 保留 Early Discovery; 进入 RA 语义修复实验 |
| Early 有效性集中于 B_PROXY_OK | 建立 **Barrier Review Shadow Gate**（机器代理+人工确认, 测试误杀/漏放）; **禁止 B_PROXY_WEAK 直接禁入 A 级** |
| F2M2 明显优于 Early | 研究 Early→Confirmed 两阶段状态设计; 不直接拆 Radar |
| Early 稳定迁移 F2M2 | 优先解释为 Growth 生命周期不同阶段 |
| Early 大量 Failure 低迁移 | L1×E0 hypothesis 降级; 研究右侧确认权重提高 |
| 结果随环境显著变化 | Regime Router 进验证议程（Audit C 不恢复） |
| B_proxy 两套定义结果冲突 | 壁垒机器代理判"不成熟", 不进 Production Gate |
| M_FULL vs RPS_ONLY 冲突 | 行业映射债 → 结论降级, 不改 Growth |

**Barrier Gate 特别纪律**: 即使 Early×B_OK >> Early×B_WEAK，正确演进路径 = 发现分层效应 → Shadow Barrier Review → 人工确认真壁垒 → 观察误杀/漏放 → 独立验证 → 才决定是否形成 Gate。防"低 PE 伪装未确认"换成"财务代理伪装护城河"的同构语义错误。

---

## 10. ⚠️v0.2 Valuation 边界（修订新增）

Audit C **不增加 V 第三轴**。理由: ① Snapshot 已确认极端估值过滤有效 ② RA 的 PE 项实质影响已确认 ③ Audit C 唯一裁决是 Growth identity ④ 历史 valuation PIT 资格未单独审计。只允许在数据资格充分时附带报告 `valuation context`，禁止构造第四维 / 重新排名 / 判定 Early-Confirmed 成败。历史估值问题另行诊断。

---

## 11. NO-GO 清单（v0.1 继承, 冻结期及 Audit C 全程）

- ❌ 修改 Growth RA / PE→E / 新建 C/M/V Production 状态 / 恢复 Regime 权重 / 修改 Growth-Recovery quota / 拆分 Growth Radar
- ❌ B_PROXY_WEAK 直接禁入 A 级（只能 Shadow Gate 路径, §9）
- ❌ 用 historical return 作一级验收 / 把 historical diagnostic 写成 historical validation
- ❌ 跳过 Pilot 直接 Full
- ❌ Pilot 阶段宣称裁决 L1×E0

---

## 12. 产出文件与提交顺序（v0.1 继承, 三段证据链独立追溯）

```
diagnostics/
  AUDIT_C_GROWTH_IDENTITY_DESIGN.md   ← 本文件 (v0.2)
  growth_identity_audit.py            (C-Pilot 实现)
  growth_identity_panel.csv           (Pilot 产物)
  growth_identity_episodes.csv        (Pilot 产物)
  growth_identity_audit_report.md     (Pilot 报告)

Commit 1: 本设计文档 (v0.2 冻结)
Commit 2: C-Pilot 代码
Commit 3: Pilot 结果与报告
→ Pilot Review (GO/FIX/NO-GO) → C-Full
```

---

*v0.2 DESIGN BASELINE — 设计原则冻结; B_proxy Mapping Gate 未关闭（§4.4）, 通过前禁止写实现代码。冻结前待决项: ① B_proxy 两套定义字段级映射 + 历史可用性勘察 ② Pilot 4 时点实际交易日确认（2023-05-10/2023-11-10/2024-09-10/2025-05-10, 交易日历顺延）。*

*提交序: Commit 1 设计基线 → Gate 0 B_proxy 映射勘察 → C-Pilot → GO/FIX/NO-GO → C-Full。*
