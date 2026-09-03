# Research Workflow Layer v2 Schema — 研究任务编排层数据契约（DRAFT v0.2）

**状态**: DRAFT v0.2（冻结期文档，不实现代码）| **日期**: 2026-09-03
**v0.2 变更记录**（v0.1 评审收敛——只改 5 处 + 2 处顺手加固，不扩展设计）:
1. Task 增加 `task_type`（与 signal_type 解耦防漂移，E/L 迁移不建任务，§5.1.1）
2. Signal 增加 `signal_id` + 落盘位置 `data/signals/` + 1:N 语义（§4.4）
3. Thesis `scope` 扩展 4 值 + 判定规则 + 存量卡归属（§1.1）
4. 历史枚举 migration mapping + legacy 边界：不可判定不猜测（§3.4）
5. Queue "排序模型" → "调度规则"（§6.1）
6. 事件记录增加 `schema_version`（枚举扩展防漂移，§3.1/§4.4）
7. 完整数据链补齐 signal_id 节点（§2）
**性质**: 数据契约——照 `OUTCOME_LEDGER_SCHEMA.md` 先例：**Schema 先冻结，实现后置**（10-02 冻结期结束后 Phase 0 实现）
**依据**: 四轮设计评审（Ranking→Allocation→Workflow 收敛）+ 存量资产源码/数据勘察（本文件所有映射均标注现有文件出处，可复核）
**定位**: 从"股票筛选系统"到"个人投资研究记忆系统"的编排层——把隐含的人类研究流程显式化为**可记录、可验证、可迭代的状态机**

---

## 0. 定位与边界

### 0.1 v2 是什么

```
Growth OS（总系统）
  ├── State Engine（L/E/P/L5/Radar — 现状，不改）
  ├── Research Workflow Layer（v2 新增编排层）
  │     ├── Thesis Layer（收编 data/thesis/，非新建）
  │     ├── Task Generator（Signal 触发）
  │     ├── Task Queue（容量+due）
  │     └── Task Events（append-only log）
  ├── Ledger（现状，加 task 挂载）
  └── Calibration（现状）
```

### 0.2 v2 不做什么（否决记录，防止回潮）

| 方向 | 结论 | 理由 |
|---|---|---|
| 综合评分/五维加权（Change×30%+...） | ❌ | RPI 坍缩两次实证；ra_score 实测 Top 区间分辨率仅 0.968-1.000；状态标签优先于评分 |
| 7 Agent LLM 委员会 | ❌ | Memo 纯规则 + Evidence Trace 是防幻觉资产；LLM 叙事不可复现 |
| Event Sourcing 重机制（Replay/Projection/Snapshot） | ❌ | 个人单用户系统：append-only JSONL + 查询聚合足够 |
| P 层升格为产业预测 | ❌ | 行业前瞻归人工（徐工/融捷实证）；P 只做范式归属 + Shadow |
| "Operating System" 命名 | ❌ | 与 Growth OS 本体冲突；本层叫 Research Workflow Layer |

### 0.3 单位映射（第一章地基——三层单位各司其职）

| 单位 | 粒度 | 回答 | 人工/机器 | 现有载体 |
|---|---|---|---|---|
| **Thesis** | 逻辑/归因单位 | "为什么值得研究？假设是什么？" | 人工创建+机器跟踪 | `data/thesis/*.yaml`（已存在） |
| **Task** | 机器验证单位 | "现在验证什么？何时截止？什么情况证伪？" | 机器生成+人工确认 | v2 新建 |
| **Company** | 人工研究会话单位 | "今天研究哪家？" | 人工 | decision_cli（维持现状） |

**为什么三层不能合并**（300308 实证）：一只公司同时存在三个独立验证点——FCC 政策（E10 事件，due=政策节点）、1.6T 价格战（E5 事件，due=季报）、毛利持续性（E4 财报，due=Q3 披露）。三者时间/数据/失败条件不同，合并为一个"研究 300308"任务 = 套话。反之，范式级 Thesis（AI Optical Cycle）跨 8 只股票共享，逐股生成任务 = 8 倍噪声。**决策纪律：人工动作按 Company 聚合（每天 3-5 只），机器验证按 Task 展开，归因统计按 Thesis 聚合。**

---

## 1. 存量资产收编（勘察结论：以现有字段为准，不重新发明对象）

> 勘察发现：**Thesis 层不是空白**。`data/thesis/` 已有两张卡，字段完整度超过此前评审假设。v2 的 Thesis Layer 工作 = 收编 + ID 化 + 连接，**不是设计新对象**。

### 1.1 Thesis 存量字段（→ Thesis Object v1 基础）

来源: `data/thesis/COHR_thesis_card.yaml` + `data/thesis/300308_shadow_lite.yaml`

| 存量字段 | 出处文件 | v2 角色 |
|---|---|---|
| `core_thesis.name/statement` | COHR | thesis.statement（范式级论点） |
| `core_assumptions[A1..A4]` / `key_assumptions[id/name/evidence/status]` | 300308 / COHR | thesis.assumptions（带 assumption 级 status: active/watch，已存在） |
| `falsify[X1..X4]` / `falsify_conditions[]` | 300308 / COHR | thesis.falsify（Task 反证的上级来源） |
| `x_monitors{policy,industry,company}` | COHR | **Signal 注册表**（§4 桥的 thesis 侧输入） |
| `market_error_type{primary,secondary}` | COHR | 错误定价分类（归因维度） |
| `evidence_status: R2_VERIFIED` | 300308 | 证据等级（R2 体系已运行） |
| `counter_evidence[]` | COHR | thesis 反方证据 |
| `price_discipline` | 300308 | 估值纪律（人工） |

**v2 需补 3 个字段（仅此而已）**：

```yaml
thesis_id: TH-20260903-001     # 缺（现仅文件名）
scope: paradigm | sector | company | hybrid   # 缺（v0.2: 4 值，判定规则见下）
status: DRAFT | ACTIVE | INVALIDATED | COMPLETED   # 缺（现仅 assumption 级 status）
```

**scope 判定规则（防分类漂移）**：`paradigm` = 跨行业产业链叙事（statement 主语是链条，如 AI Optical Cycle）；`sector` = SW 行业级周期（主语是行业，如半导体设备周期）；`company` = 单公司特有假设（core_question 只适用于该公司）；`hybrid` = 范式背景 × 公司定位（两者皆为主语）。存量卡归属示例：COHR 卡 = `hybrid`（AI 光互联需求 → 公司平台化）；300308 Lite 卡 = `hybrid`（范式级 A1 + 公司级证伪 X1-X4）。

### 1.2 判断/决策存量（→ 四层事件字段，§3）

来源: `data/ledger/decisions.jsonl`（19 条实测）+ `tools/decision_cli.py` + `tools/validation_overlay.py`

| 层 | 存量枚举（实测） | v2 处理 |
|---|---|---|
| L1 工作流动作 | 无（v2 新建） | task_status: OPEN/SCHEDULED/DONE/SKIPPED/STALE |
| L2 人工判断 | decision_cli: `WATCH/IGNORE/BUY_CANDIDATE/RESEARCH_REQUIRED/UNKNOWN`；ledger schema: `buy/watch/pass`；overlay human: `QUALITY_OBSERVE/IGNORE_PENDING/WATCH_RESEARCH/...`（自由文本） | **统一为 decision_cli 枚举**（收编另两套；overlay 状态保留为"人工状态标签"不并入） |
| L3 人机关系 | decision_type 9 种: `MODEL_CONFIRM/MODEL_EXCEPTION_V2/MODEL_DISAGREEMENT/HUMAN_INITIAL_JUDGMENT/AI_ASSISTED_JUDGMENT/POLICY_EXCLUSION/MODEL_MIXED/PROBE_FALSE_POSITIVE` | 保留（四象限归因原料） |
| L4 来源 | `created_by: human/AI_ASSISTED`（实测 13/19 为 None） | task 创建时自动继承（来源缺失问题消失） |

**关键语义**：四层是**四个字段**，不是一列枚举。硬合并会丢失"人机关系"（归因）与"人工状态标签"（Overlay 叙事）语义。

### 1.3 Ledger 存量（直接复用为 t2 判定层，不重建）

来源: `docs/OUTCOME_LEDGER_SCHEMA.md`（已冻结）+ `growth_os/ledger.py`（已实现 init/backfill/review）

| 存量对象 | 文件 | v2 复用 |
|---|---|---|
| ResearchOutcome（price/state/thesis/evidence 四类回填） | outcomes.jsonl（100 条历史） | Task DONE 后的 t2 数据源 |
| InvestmentDecision（decision_id/decision/reason） | decisions.jsonl | 收编 L2 枚举 |
| ThesisReview（price_verdict/state_verdict/thesis_verdict/attribution/learning） | reviews.jsonl | **Thesis status 流转的裁判**（§5） |

**现成先例——Evidence 自动回填**：300308 记录的 `interim_validation`（2026Q2 中报 revenue_yoy +182% 自动核验）已示范"验证点自动比对"。v2 把它从 decision 记录提升为 Task 的 `evidence_result` 槽位。

### 1.4 事件层存量（Signal 采集侧，已存在）

来源: `tools/event_scan.py` E1-E18 taxonomy（E1订单/客户 … E18市场情绪 + 公司事件兜底）+ HIGH_RISK_KEYWORDS（FCC/禁令/制裁/立案/减持…）；`tools/daily_event_collector.py`（akshare 公告 + AnySearch + 财联社 → `data/events/*.jsonl`）；`data/cache/disclosure_calendar.csv`（5508 只实际公告日）

---

## 2. 统一 ID 体系

> 勘察发现的最大结构性缺口：**thesis 无 id、decision 无 task_id、outcome_id 挂股票不挂 thesis**——全链路无法追溯"哪个假设 → 哪个验证 → 哪个判断"。

| ID | 格式 | 挂载 | 现状 |
|---|---|---|---|
| `thesis_id` | `TH-YYYYMMDD-NNN` | Thesis 对象 | 缺（新建） |
| `signal_id` | `SG-YYYYMMDD-NNN` | Signal 事件（§4.4） | 缺（新建） |
| `task_id` | `TK-YYYYMMDD-NNN` | Task 事件 | 缺（新建） |
| `outcome_id` | `RO-YYYYMMDD-code` | ResearchOutcome | ✅ 已有（ledger.py） |
| `decision_id` | `ID-YYYYMMDD-code` | InvestmentDecision | ✅ schema 已有 |

**挂载规则**：
- Task 必须挂 `thesis_id`（无 Thesis 的任务禁止入队——任务生成器第一约束）
- Task 可选挂 `code`（Company 载体；范式级 Thesis 的共享 Task 不挂单一 code，挂 thesis 成员列表）
- decision 记录新增 `task_id` 字段（可选——人工例外判断可不经 task，此时 relation=MODEL_EXCEPTION_V2 类；v0.1 笔误修正）
- outcome 新增可选 `thesis_id`（现挂 stock，兼容保留）

**完整数据链（v0.2 冻结——任何环节缺 id 即断链）**：

```
Thesis (thesis_id) ← 人工/范式级
  ↓
Signal (signal_id) ← x_monitors × 事件层命中（§4.4）
  ↓
Task (task_id) ← 生成器，挂 thesis_id [+ code]
  ↓
Decision (decision_id) + Evidence (evidence_result)
  ↓
Outcome (outcome_id)
  ↓
ThesisReview → thesis status 流转
```

---

## 3. 四层事件 Schema + Append-only Event Log

### 3.1 记录格式（追加式 JSONL，沿用 decisions.jsonl 模式）

```json
{
  "schema_version": "2.0",
  "event_id": "EV-20260903-0001",
  "task_id": "TK-20260903-001",
  "signal_id": "SG-20260903-001",   // CREATED 事件必填；人工例外为 null
  "event_type": "STATUS_CHANGE",
  "from_state": "OPEN",
  "to_state": "SCHEDULED",
  "actor": "SYSTEM",
  "reason": "DISCLOSURE_WINDOW",
  "timestamp": "2026-09-03T09:30:00"
}
```

当前状态 = 按 task_id 聚合查询（**不做** Event Replay/Projection/Snapshot——个人系统过重）。

### 3.2 Task 事件类型（MVP）

| event_type | from → to | actor | 触发 |
|---|---|---|---|
| CREATED | — → OPEN | SYSTEM/HUMAN | Signal 命中 / 人工例外 |
| SCHEDULED | OPEN → SCHEDULED | SYSTEM | Queue 排期（due 分配） |
| DONE | SCHEDULED → DONE | HUMAN | decision_cli 动作留痕 |
| SKIPPED | OPEN/SCHEDULED → SKIPPED | HUMAN | 人工主动拒绝（= 四象限 B 象限） |
| STALE | 任意 → STALE | SYSTEM | due 过期未处理 |

### 3.3 Judgment 事件（人工判断，与 Task 事件分离）

```json
{
  "decision_id": "ID-20260903-600338",
  "task_id": "TK-20260903-002",
  "judgment": "WATCH",
  "relation": "MODEL_CONFIRM",
  "source": "HUMAN",
  "thesis": "…", "counter": "…", "check": "Q3",
  "confidence": "M"
}
```

judgment 统一为 decision_cli 枚举：`WATCH / IGNORE / BUY_CANDIDATE / RESEARCH_REQUIRED / UNKNOWN`（收编 ledger schema 的 buy/watch/pass；overlay 的 QUALITY_OBSERVE 类保留为人工状态标签字段 `human_state`，不并入 judgment）。

### 3.4 历史枚举 Migration（v0.2 新增——旧数据 immutable，新数据 normalized）

| 旧值 | 出处 | → 新 judgment |
|---|---|---|
| `buy` | OUTCOME_LEDGER_SCHEMA InvestmentDecision.decision | `BUY_CANDIDATE` |
| `watch` | 同上 | `WATCH` |
| `pass` | 同上 | `IGNORE` |
| `DEEP_RESEARCH` 等自由文本 | decisions.jsonl human_decision.decision（实测） | **不映射** → `UNKNOWN` + 原文保留 `legacy_decision` 字段 |
| `QUALITY_OBSERVE` 等 | overlay state.yaml human | 不并入 judgment → 保留 `human_state` 字段 |

**legacy 边界（防语义污染）**：migration 只做**词级等价**映射；自由文本决策不做语义猜测（DEEP_RESEARCH → RESEARCH_REQUIRED 是猜测，会污染四象限归因）。历史行 **不 rewrite**（immutable），migration = 生成 normalized 派生视图，原文件不动。实测 19 条 decisions 中仅 4 条有 action 字段、其余走 decision_type/human_decision 自由文本——Phase 0 按此口径处理。

---

## 4. Signal 桥（x_monitors × 事件层 × 披露日历 → Task 触发）

> **勘察关键发现**：Signal Engine 的输入源已存在但从未连接——COHR 卡的 `x_monitors`（人工定义关注什么）与 event_scan 的 E1-E18 + disclosure_calendar（机器采集）之间没有线。

### 4.1 A 池与 Signal 的分工（防 551 任务化）

| 机制 | 输入 | 覆盖 | 节奏 |
|---|---|---|---|
| 静态轮转（现状） | A 级池按范式/行业分桶 | 551 全覆盖 | 周轮（防遗忘） |
| 动态触发（v2） | **Signal** | 命中少数 | 事件驱动 |

**A 池是候选空间，Signal 是任务触发器。** 无信号的 A 级股票不进队列，只进轮转桶。

### 4.2 Signal 类型（对齐现有枚举，不新建体系）

| Signal | 检测源（存量） | 触发语义 |
|---|---|---|
| EVENT_HIT | `EVENT_CATEGORIES` E1-E18 关键词命中 × `x_monitors` 匹配 | 事件进入 thesis 关注域 |
| DISCLOSURE_WINDOW | `disclosure_calendar.csv`（5508 只实际公告日） | 财报披露窗口临近（hard due 来源） |
| E_STATE_CHANGE | `expectation_state.py`（E0-E3） | 认知状态迁移（如 E0→E1） |
| L_STATE_CHANGE | `state_machine.py`（L0-L5） | 生命周期迁移 |
| L5_TRIGGER | `l5_recovery.py` 四层判定 | 错杀候选出现 |
| HUMAN_EXCEPTION | decision_cli / overlay 人工 | 人工发现（300308 类，relation=MODEL_EXCEPTION_V2） |
| FALSIFY_HIT | （v2.1）falsify 自动比对 | thesis 证伪条件命中（先例: interim_validation） |

### 4.3 x_monitors 升级为 Signal 注册表

```
Thesis 卡 x_monitors（人工）           Signal 采集（机器）
  policy: [FCC, 出口管制, InP限制]  ×   event_scan E10/E16 关键词
  industry: [1.6T价格, 云capex]     ×   event_scan E5/E14 关键词
  company: [FY27Q1财报, PhotonLink] ×   disclosure_calendar + E2/E9
                ↓ 命中
          Signal 事件 → Task Generator → Task（挂 thesis_id）
```

**副作用（重要）**：此桥同时解决"Thesis 如何保持活跃"——thesis 通过 x_monitors 持续接收事件，而非躺着等人工回访。

### 4.4 Signal 事件记录（v0.2 新增——桥的落盘与血缘）

```json
{
  "schema_version": "2.0",
  "signal_id": "SG-20260903-001",
  "signal_type": "EVENT_HIT",
  "thesis_id": "TH-20260903-001",
  "matched_monitor": "policy.FCC",
  "source_event": "E10 政策/监管 命中",
  "raw_ref": "data/events/20260903_events.jsonl#L3",
  "timestamp": "2026-09-03T09:30:00"
}
```

- **落盘位置**: `data/signals/YYYYMMDD_signals.jsonl`（原始事件在 `data/events/`，signal 是"事件×monitor 匹配"的派生记录，分层存储）
- **1:N 语义**: 一个 Signal 可触发多个 Task（范式级 signal → thesis 成员公司各自的验证任务，或一个共享任务挂 thesis 不挂 code）——task 的 CREATED 事件带 `signal_id`，允许多 task 引用同一 signal
- **无 signal 的任务**: 仅 HUMAN_EXCEPTION（人工例外，`signal_id: null`）

---

## 5. Task 生成规则与质量门槛

### 5.1 生成器输入输出

```
输入: Signal 事件 + thesis_id + Company 载体 + 范式模板（L×范式×探针状态分桶）
输出: Task {task_type, question, evidence_required[], falsify_condition, deadline}
```

### 5.1.1 task_type（v0.2 新增——统计"哪类任务贡献高"的结构化前提）

**task_type 描述"任务动作"，signal_type 描述"触发原因"——两枚举解耦，防漂移**：

| task_type | 动作语义 | 默认触发 signal | 启用 |
|---|---|---|---|
| `EVENT_VALIDATION` | 验证事件是否改变 thesis | EVENT_HIT | MVP |
| `DISCLOSURE_CHECK` | 财报核验（hard due 来源） | DISCLOSURE_WINDOW | MVP |
| `RECOVERY_RECHECK` | 错杀恢复复查 | L5_TRIGGER | 随 L5 信号接通 |
| `HUMAN_EXCEPTION` | 人工例外（无 signal） | — | MVP |
| `THESIS_FALSIFY` | 证伪条件自动核验 | FALSIFY_HIT | v2.1 |

**E_STATE_CHANGE / L_STATE_CHANGE 不新建任务**：状态迁移是对既有研究问题的**再定价**——触发既有 OPEN task 的 priority/due 属性更新（非 STATUS_CHANGE）；无既有 task 时降级为决策提示转人工（HUMAN_EXCEPTION 候选）。防"状态一迁移就批量建任务"的噪声。

### 5.2 质量门槛（分两段——前置结构校验，后置行为指标）

**前置（自动，schema 级，不判语义）**：
- G1 可判定性：`falsify_condition` 必须为可判定结构——`字段 + 比较符 + 阈值 + 时间窗`
  - ✅ `revenue_yoy_q3 < 0.5`（2026Q3 营收同比 <50% → 假设降级）
  - ❌ "关注需求下降风险"
- G2 证据可引用：`evidence_required[]` 必须引用数据资产清单现有项（tdx 财务字段/E1-E18 类别/披露日历），不引用即不入队
- G3 归属：必须挂 thesis_id

**后置（行为指标，滞后反馈）**：人工改写率——自动任务被人工修改文本的比例 >30% → 模板库质量差，回炉模板。**机器不判"研究问题好不好"——那是投资判断，归人工。**

### 5.3 Task 状态机（MVP，刻意不全）

```
                    HUMAN_EXCEPTION
                         ↓
        OPEN ──→ SCHEDULED ──→ DONE
         │          │
         │          └──→ SKIPPED（人工主动拒绝）
         └──→ STALE（due 过期，自动）
```

**SKIPPED ≠ STALE（语义必须分开）**：

| 状态 | 含义 | 归因价值 |
|---|---|---|
| SKIPPED | 人工看了、主动拒绝 | 四象限 B 象限（系统推荐+人拒）；对生成器最干净的实时反馈 |
| STALE(reason=NO_TIME) | 容量不足，任务本身 OK | 容量模型输入 |
| STALE(reason=LOW_VALUE) | 任务质量差 | 生成器失败信号 |
| STALE(reason=DUPLICATE) | 与其它任务重复 | 生成器去重反馈 |

**延后到 v2.1（不提前接通）**：`DONE → VALIDATING → CONFIRMED/REJECTED`——裁判依赖 T+90 ThesisReview 流程（reviews.jsonl）成熟度；现在接通会产生僵尸 VALIDATING 任务。falsify 命中可自动**候选** REJECTED，最终确认由 review 驱动。

---

## 6. Queue 视图（薄视图，非排序引擎）

### 6.1 调度规则：Priority × Due 二维，取消 P0/P1/P2 三档

| 变量 | 语义 | 更新频率 |
|---|---|---|
| `priority` | 静态研究价值（生成时定，来自触发信号类型 + thesis 状态） | 低频 |
| `due` | 动态窗口（hard: 披露日历实际公告日；soft: 事件窗口估计） | 动态 |

队列规则：**容量内先处理 due 最近的；due 相同按 priority**。例：Priority 高但 due 半年后 vs Priority 中但 due 明日财报 → 先做后者。

### 6.2 配额（维持 Radar-Quota 思路，防 L5 霸榜）

Top 区间实测 recovery_radar 占 7/10（ra_score 1.000-0.968 区间 L5 主导）——配额保留：Growth / Recovery / 范式 Shadow / 人工例外分桶。v2.0 不扩展配额体系，维持现状双桶 + 人工例外通道。

### 6.3 人工入口（Company 聚合视图）

decision_cli 增加 `--queue` 入口：按 Company 聚合展示其 OPEN/SCHEDULED Tasks（1 家公司 1-3 个任务 = 一次研究会话），动作选择后 task → DONE/SKIPPED + judgment 事件落盘。**30 秒纪律不破坏**：judgment 必填，task 关联自动，其余可选。

---

## 7. 与 Ledger / Calibration 衔接

### 7.1 数据流

```
Task DONE（含 judgment 事件）
  ↓
outcomes.jsonl 自动回填（T+30/90/180/365: price/state/probes — ledger.py 已实现）
  ↓
T+90 ThesisReview（reviews.jsonl: price_verdict/state_verdict/thesis_verdict/attribution）
  ↓
Thesis status 流转（ACTIVE → COMPLETED/CONFIRMED 或 INVALIDATED）← 裁判是 review，非自动
  ↓
Calibration（CAL 样本：失败任务入 attribution 分析）
```

### 7.2 四象限归因口径（统计时点 t0/t1/t2）

| 象限 | 定义 | 数据来源 |
|---|---|---|
| A 系统对 | 系统推荐(Task 生成) + 人工接受 + 验证成立 | task CREATED + judgment + review |
| B 系统错 | 系统推荐 + 人工拒绝(SKIPPED) + 后续验证成立 | SKIPPED + review |
| C 人工对 | 人工发现 + 系统未发现（300308 类） | relation=MODEL_EXCEPTION_V2（例外通道，样本天然小，接受个位数/季） |
| D 双方错 | 系统推荐 + 人工接受 + 验证失败 | review verdict=failed |

**t0 快照必录**（埋点先行）：Task 生成日的 L/E/P/ra_score/触发 Signal/证据——v3.5 Ledger 缺 t0 快照字段，Phase 0 补。

**统计陷阱预防**：命中率必须按 系统∩人工 / 人工only / 系统only 分层——人工挑着研究的选择偏差会污染单一"Top10 命中率"。

---

## 8. 冻结与验收

### 8.1 时间线

```
2026-09-03 ~ 10-02（冻结期）: 本 schema 冻结（DRAFT→v1 评审）；代码零改动；
                              每日三命令照常积累判断样本（目标 ~100 条）
10-02 起 Phase 0（~1 周）:    统一 schema + t0 快照埋点 + quarantine 池正式化（先于一切队列代码）
Phase 1:                     Task Generator（Signal 桥 + 结构门槛）
Phase 2:                     Queue 视图（--queue 入口）
Phase 3:                     Ledger 聚合（四象限 + thesis 命中率）
v2.1（90 天后）:              完整状态机接通 + falsify 自动比对（FALSIFY_HIT）
```

### 8.2 v2 规则自带冻结（防"反馈周期未到就改规则"污染样本）

Task 生成规则 + Queue 规则在 Phase 1 上线后 **90 天不变**（照 P 层 Shadow 30 天 + 运行期冻结先例；90 天因 t2 反馈周期更长）。

### 8.3 验收端点（回答"系统有没有用"）

| 端点 | 定义 | 判定 |
|---|---|---|
| 任务完成率 | DONE/(DONE+SKIPPED+STALE) | 反映容量匹配（STALE=NO_TIME 过高 → 队列过载） |
| thesis 命中率 | review verdict=confirmed 比例（按 thesis 聚合） | 反映假设质量 |
| 改写率 | 人工修改任务文本比例 | >30% → 模板回炉 |
| SKIPPED 率 | SKIPPED/(SKIPPED+DONE) | 反映生成器 precision |
| A 级覆盖率 | 551 只中已生成任务的占比（轮转覆盖） | 防头部垄断 |

**不做**：CAGR/Sharpe/胜率作为第一端点（研究系统验收 = 假设命中，非收益预测——Appendix A 定位校准已确认）。

---

## 附录 A：存量文件 → v2 角色映射总表

| 现有文件 | 角色 | v2 动作 |
|---|---|---|
| `data/thesis/*.yaml`（2 张卡） | Thesis Object 存量 | 补 thesis_id/scope/status，目录化 |
| `data/ledger/decisions.jsonl` | 判断事件流 | 加 task_id/judgment 统一 |
| `data/ledger/outcomes.jsonl` + `reviews.jsonl` | t2 回填/裁判 | 复用（100 条历史已跑通） |
| `data/overlay/state.yaml` + `transitions.jsonl` | 人工状态叠加 | human_state 字段保留，不并入 judgment |
| `tools/decision_cli.py` | 人工入口 | 加 --queue 聚合视图 |
| `tools/event_scan.py`（E1-E18 + HIGH_RISK） | Signal 采集 | 与 x_monitors 接线 |
| `tools/daily_event_collector.py` | 事件入库 | 复用 |
| `data/cache/disclosure_calendar.csv` | hard due | 复用 |
| `growth_os/expectation_state.py` / `state_machine.py` / `l5_recovery.py` | Signal 源（状态迁移） | 复用，不改 |
| `output/research_book_*.csv` | Task 生成的 Book 侧输入 | ra_score 仅作 t0 快照记录，不作队列排序 |
| `output/growth_pool_quarantine_*.csv` | 四象限 C 负例存档 | 正式化 |

## 附录 B：评审历程差异记录（防文档漂移）

| 轮次 | 提案 | 结论 | 本文件位置 |
|---|---|---|---|
| R1 | Top10 Research Ranking Engine + 五维评分 | ❌ 评分否决；方向（压缩层）采纳 | §0.2, §6 |
| R2 | Allocation v2（分配器） | ✅ 概念采纳，改名 Workflow Layer | §0.1 |
| R3 | Thesis 中间层 + Signal 触发 | ✅ 采纳（勘察证明 thesis 已存在，收编替代设计） | §1, §4 |
| R4 | 完整 Event Sourcing / Task Quality Gate 前置语义 | ❌ 机制简化；Gate 分前后两段 | §3.1, §5.2 |

---

*DRAFT v0.2 冻结期评审稿。下一步：10-02 冻结期结束前评审本契约（v0.2 后不再扩展设计）；Phase 0 实现以本文件为数据契约（照 OUTCOME_LEDGER_SCHEMA 先例）。*
