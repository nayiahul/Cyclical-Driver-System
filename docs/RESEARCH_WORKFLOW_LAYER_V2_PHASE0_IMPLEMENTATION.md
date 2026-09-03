# Research Workflow Layer v2 — Phase 0 实施清单（Implementation Baseline v0.2）

**状态**: Implementation Baseline v0.2 | **日期**: 2026-09-03 | **性质**: 实施映射文档（勘察驱动，非设计文档）
**v0.2 变更**: ① 新增 §7 Characterization Validation Record（T-WF-01/02 验收证据, 16/16 GREEN）② §5 测试表拆分为"已落地/10-02 后"并修正落点（tests/workflow/, 命名遵循 pytest 收集规则）③ 附录文件清单同步 ④ 状态从 DRAFT 提升为 Implementation Baseline（schema/测试边界冻结, 不再扩展设计）
**上游契约**: `RESEARCH_WORKFLOW_LAYER_V2_SCHEMA.md` v0.2（本文件不改变冻结 schema，只做 代码↔schema 映射）
**适用范围**: 10-02 冻结期结束后 Phase 0（~1 周）| **勘察范围**: `growth_os/ledger.py` + `tools/decision_cli.py` + `data/overlay/`（已勘察完毕）

---

## 0. 实施原则

1. **不改变冻结 schema**（v0.2 为契约；本文件发现 1 处需 v0.2.1 勘误，见 §0.2）
2. **不修改历史数据**（immutable）：migration = 生成 normalized 派生视图，原文件 sha 不变
3. **新旧并行**：现有 `--book/--stock/--quick` 路径零改动，只新增 `--queue` 入口
4. **30 秒纪律不破坏**：judgment 必填，task 关联自动，其余可选
5. 每改动点标注源文件函数（勘察依据），无标注的改动禁止进入 Phase 0

## 0.1 勘察结论（三落点事实）

| 落点 | 现状事实（代码级） | 对 Phase 0 的含义 |
|---|---|---|
| `ledger.py:init_from_book` | t0 已存: outcome_id/stock/memo_date/radar/**lifecycle_state**/confidence/**ra_score**/created_at + 4 个结果容器骨架 | t0 快照**部分已存在**——缺 E/P 状态（见 §3） |
| `ledger.py:backfill/generate_review` | t90 回填 price/state/probes；verdict=confirmed/partial/failed；attribution 骨架 | t2 判定层已可用，Phase 0 不动 |
| `ledger.py` 查重 | `init_from_book` 每行全量 `_load("outcomes.jsonl")`（O(n²) 模式） | 量级 100 条，**不动**（记录在案） |
| `decision_cli.py:save` | **单写** decisions.jsonl（append）；无 overlay 双写 | --queue 新增无写冲突 |
| `decision_cli.py` 字段 | stock/name/action/thesis/counter/check/confidence/date/created_at/status | 缺 task_id/relation/source（§4 补） |
| `validation_overlay.py:log_transition` | transitions.jsonl = `{date,code,machine,human,signal_type,evidence,author}`——**非 from/to 状态机**；overlay 是独立 CLI（--add/--status） | overlay 系统独立保留，**不迁移**（v0.2 §3.3 human_state 结论确认） |
| `state.yaml` | code → {machine, human, signal_type, evidence, updated}；machine 形如 `L1_Growth_A`/`L0_Shadow_P2` | 只读参考，不写 |

## 0.2 Schema 冲突发现（v0.2.1 勘误，实施前回注 v0.2 文档）

**`signal_type` 同名不同义**：
- v0.2 §4.2 定义 v2 Signal 类型：`EVENT_HIT / DISCLOSURE_WINDOW / E_STATE_CHANGE / L_STATE_CHANGE / L5_TRIGGER / HUMAN_EXCEPTION / FALSIFY_HIT`
- `validation_overlay.py` L33-41 已存在 `SIGNAL_TYPES`：`LOW_BASE_BIAS / CYCLE_BETA / QUALITY_GROWTH / QUALITY_VALUATION / VALUATION_COMPRESSION / MACRO_RELATED / POLICY_RISK / UNCLASSIFIED`（CAL 教训分类，存量 3 条 transitions + state.yaml 在用）

**解决**：v2 新字段改名 **`trigger_type`**（新系统改名成本最低；overlay 存量数据 immutable 不能动）。v0.2 中 §4.2/§4.4/§5.1.1 的 signal_type 实施时一律以 `trigger_type` 落地；overlay 的 `signal_type` 保留原名（人工信号分类，语义独立）。Phase 0 文档、代码、测试统一用 `trigger_type`。

---

## 1. 数据迁移

### 1.1 decisions.jsonl → decisions_normalized.jsonl（派生视图，原文件不动）

- 输入: `data/ledger/decisions.jsonl`（实测 19 条，其中 4 条有 action 字段）
- 输出: `data/ledger/decisions_normalized.jsonl`
- 规则（照 v0.2 §3.4，只做词级等价）:
  - 词级映射: `buy→BUY_CANDIDATE` / `watch→WATCH` / `pass→IGNORE`（ledger schema 值）
  - `action` 字段（decision_cli 值）→ 直接作为 judgment
  - 自由文本（human_decision.decision 如 DEEP_RESEARCH）→ `judgment: "UNKNOWN"` + 原文保留 `legacy_decision`
  - `relation` 从 decision_type 派生（可判定时）: MODEL_CONFIRM→`MODEL_CONFIRM`、MODEL_EXCEPTION_V2→`MODEL_EXCEPTION_V2`（即保留原值）；无 decision_type → null
  - `source` 从 created_by 派生: human/AI_ASSISTED 保留；None → `UNKNOWN`（不猜）
- 新脚本: `tools/migrate_decisions_v2.py`
  - 读原文件 → 逐行 normalize → 写派生文件（覆盖式，幂等，从原文件重生成）
  - 输出迁移报告: `n 条 → n 条（无丢失）、m 条 UNKNOWN（附 legacy_decision）、k 条 source=UNKNOWN`
- **验收断言**: 原文件 sha256 不变（测试 T-WF-02）

### 1.2 Thesis 迁移（2 张 yaml 补 3 字段）

| 文件 | thesis_id | scope | status |
|---|---|---|---|
| `data/thesis/COHR_thesis_card.yaml` | `TH-20260903-001` | hybrid | ACTIVE |
| `data/thesis/300308_shadow_lite.yaml` | `TH-20260903-002` | hybrid | ACTIVE |

- 每张卡文件头加注释行: `# thesis_id / scope / status (Research Workflow v2, 2026-09-03)`
- 校验: `tools/validate_thesis_v2.py`（结构 lint: id 唯一 / scope 枚举 4 值 / status 枚举 4 值）——两张卡手动改 + lint 校验，不写迁移框架

### 1.3 Overlay / 历史 ledger / reviews.jsonl：**零迁移**

transitions.jsonl、state.yaml、outcomes.jsonl（100 条）、reviews.jsonl（100 条）全部 immutable，Phase 0 不触碰。

---

## 2. ID 生成规则（冻结，v0.2 §2 实施）

| 前缀 | 格式 | 生成位置 |
|---|---|---|
| `TH-` | TH-YYYYMMDD-NNN | thesis 卡人工分配（2 张存量已分） |
| `SG-` | SG-YYYYMMDD-NNN | （Phase 1 Signal 桥启用，Phase 0 预留） |
| `TK-` | TK-YYYYMMDD-NNN | 新 `growth_os/workflow/ids.py` |
| `EV-` | EV-YYYYMMDD-NNN | 同上 |
| `RO-` | RO-YYYYMMDD-code | ✅ 已有（ledger.py:init_from_book） |
| `ID-` | ID-YYYYMMDD-code | ✅ schema 已有 |

- 新模块: `growth_os/workflow/__init__.py` + `ids.py`（next_id(prefix) 函数：读当日计数 → 原子递增 → 返回）
- **不可复用规则**: ID 一旦生成不回收；生成失败（写盘中断）用新 ID 重试，不回填旧 ID

## 3. t0 Snapshot 补齐（v0.2 §7.2 实施）

### 3.1 勘察事实: 一半已存在

`ledger.py:init_from_book` 已存: code / memo_date / radar / **L 状态**(state_at_memo) / confidence / **ra_score** / green probes（evidence_effectiveness.green_probes_at_memo）

### 3.2 缺口: Book CSV 有列但未入库

Book CSV（research_book_*.csv 实测列）含 `expectation_state / paradigm / p_state`，`init_from_book` **未写入** outcomes.jsonl。

**改动（最小）**: `ledger.py:init_from_book` 的 rec 增加 3 字段（读 CSV 列，`.get()` 容错）:

```python
"expectation_state": str(row.get("expectation_state", "")),  # E 状态
"paradigm": str(row.get("paradigm", "")),                    # P 范式名（空=未命中）
"p_state": str(row.get("p_state", "")),                      # P 状态（空=非 Shadow 标的）
```

- 向后兼容: 只影响**新写入**的记录；存量 100 条不 rewrite（immutable）
- 测试: T-WF-04

### 3.3 Task CREATED 事件即 t0 snapshot 载体

`data/ledger/task_events.jsonl`（新文件），CREATED 事件字段（v0.2 §3.1 + snapshot 要求）:

```json
{
  "schema_version": "2.0",
  "event_id": "EV-20260903-0001",
  "task_id": "TK-20260903-001",
  "event_type": "CREATED",
  "trigger_type": "DISCLOSURE_CHECK",
  "thesis_id": "TH-20260903-001",
  "signal_id": null,
  "code": "600338",
  "created_at": "2026-09-03T09:30:00",
  "snapshot": {"L": "L1", "E": "E0", "P": "", "P_state": "", "ra_score": 0.988},
  "evidence_refs": ["tdx:contract_liabilities", "E1订单/客户"]
}
```

- 落盘函数: `growth_os/workflow/events.py`（append_event / load_events / aggregate_by_task 三个函数，JSONL 追加 + 查询聚合，无重放引擎）

## 4. decision_cli 改造（--queue 入口，现有路径零改动）

### 4.1 流程（Company 会话 = 一次研究会话单位，v0.2 §6.3）

```
python tools/decision_cli.py --queue
  ↓ 读 task_events.jsonl 聚合 OPEN/SCHEDULED task
  ↓ 按 code 分组展示（Company 会话: 1 家 1-3 task + thesis 上下文）
  ↓ 动作选择（复用 ACTIONS 5 值 + 反证必填，沿用 interactive() 30 秒结构）
  ↓ 双写:
     task_events.jsonl  ← DONE/SKIPPED 事件（task_id 关联）
     decisions.jsonl    ← 现有格式 + task_id/relation/source 新可选字段
```

### 4.2 新字段（decisions.jsonl 追加，向后兼容——旧消费者忽略未知键）

```python
# decision_cli.py save() 调用处（queue 路径）附加:
rec["task_id"] = task_id        # 关联 task
rec["relation"] = "MODEL_CONFIRM"  # 经 task 路径的默认关系
rec["source"] = "HUMAN"         # 来源（task 创建时已继承，人工确认）
```

- relation/source 仅 --queue 路径写入；--book/--stock/--quick 路径**不加字段**（保持现状输出，30 秒纪律与既有数据格式零变化）
- 去重: --queue 沿用现有 done-set（按 stock 跳过已录），task 维度用 DONE/SKIPPED 事件去重

### 4.3 人工例外通道（C 象限采集不能断）

- `--queue --add CODE` : 创建 HUMAN_EXCEPTION task（trigger_type=HUMAN_EXCEPTION, signal_id=null, thesis_id 必填或提示先建卡）→ 进入同一交互
- 300308 类例外不再需要散落手工 JSON——走统一通道

### 4.4 明确不做（Phase 0）

- Signal 桥接线（Phase 1: x_monitors × event_scan → SG- 事件）
- 任务生成器模板库（Phase 1）
- 四象限统计聚合（Phase 3，等 t2 数据积累）
- **quarantine 池正式化**（v0.2 §8.1 原列 Phase 0——本文件范围收敛，移至 Phase 0b：quarantine CSV 格式需独立勘察，不阻塞 schema/CLI 主线）

## 5. 测试（Gate 1 characterization 先例: 先 RED 后 GREEN）

新文件 `tests/workflow/test_wf_01_decision_normalization.py` + `test_wf_02_chain_integrity.py`（命名遵循 pytest 默认 `test_*.py` 收集规则；无 pytest.ini 自定义）:

**已落地（2026-09-03, 16/16 GREEN — 证据见 §7）**:

| 用例 | 断言 | 状态 |
|---|---|---|
| T-WF-01 (9 用例) | migration 规则（词级映射/action 直通/自由文本不猜/overlay 隔离/source 归一）+ 真实 19 条不变量（无损/UNKNOWN 纪律）+ 原文件不可变 | ✅ GREEN |
| T-WF-02 (7 用例) | id 链正断言（outcome/review 闭包 100%）+ 断链点钉住（thesis/task/outcome/signal/task_events 缺口） | ✅ GREEN |

**10-02 后实现（RED → GREEN）**:

| 用例 | 断言 | 状态 |
|---|---|---|
| T-WF-03 ID 生成 | 1000 次 next_id 无重复 + 格式 regex `^(TK\|EV)-\d{8}-\d{3}$` | RED（无 ids.py） |
| T-WF-04 t0 补齐 | init_from_book v2 写入含 expectation_state/paradigm/p_state | RED（现代码无此 3 字段） |
| T-WF-05 --queue 落盘 | mock stdin 完成一次会话 → task_events.jsonl 出现 DONE + decisions.jsonl 新增行含 task_id | RED（无 --queue） |
| T-WF-06 回归 | 既有 characterization 全部仍 GREEN（--book/--stock/--quick 路径零改动） | 基线 GREEN |

## 6. Phase 0 验收清单（非收益指标）

- [ ] migration 通过: 19 条 → 19 条无丢失；UNKNOWN 计数报告落盘
- [ ] normalized 视图幂等重跑（两次运行结果一致）
- [ ] thesis 2 卡补字段完成 + `validate_thesis_v2.py` 通过
- [ ] task_events.jsonl 可写可聚合（append_event/aggregate_by_task 单测）
- [ ] CLI `--queue` 可完成一次 Company 会话（DONE 事件 + judgment 落盘双写验证）
- [ ] 既有 29 测试全 GREEN（回归）
- [ ] 历史文件 sha 不变: decisions.jsonl / transitions.jsonl / state.yaml / outcomes.jsonl / reviews.jsonl
- [ ] v0.2.1 勘误回注: v0.2 §4.2/§4.4/§5.1.1 的 signal_type → trigger_type

**Phase 0 边界（不做）**: Signal 桥、任务生成器、模板库、四象限统计、quarantine 正式化（Phase 0b）、VALIDATING 状态机（v2.1）、任何 L/E/P 决策逻辑改动。

---

## 7. Characterization Validation Record（验收证据, 2026-09-03）

### 7.1 测试目的

本阶段测试**不是 TDD 新功能测试**，而是 characterization：

> 验证 v2 schema 是否能**无损承载当前真实数据结构**（证明"可以迁移"，而非"已经迁移"）。

范围约束：不修改生产数据（原文件不变断言）· 不生成正式 task · 不改变 Ledger · 不影响运行期 · 全离线无网络（conftest 纪律）。

### 7.2 T-WF-01 Decision Normalization — 9/9 PASS

- 输入: `data/ledger/decisions.jsonl`（19 条, 实测 4 种格式并存: action 直通 4 / human_decision.decision 11 / 顶层 decision 4）
- 输出: normalized 派生视图（legacy 嵌套全量保留）
- 真实数据结果: `WATCH 5 / IGNORE 5 / RESEARCH_REQUIRED 2 / UNKNOWN 7`；relation(decision_type) 保留 18/19；source 6 HUMAN + 13 UNKNOWN；无损 100%（53 键全覆盖）
- **关键纪律（固化进测试, 未来 migrate 脚本必须对齐）**:
  1. **无损原则**: normalized 的 legacy 嵌套必须覆盖原记录全部键
  2. **UNKNOWN 纪律**: 无明确词级映射不做语义猜测——UNKNOWN 必带 `legacy_decision` 原文（DEEP_RESEARCH×4/IGNORE_ALL/IGNORE_PENDING/WATCH_RESEARCH 均不映射; overlay 状态词与 judgment 语义隔离）
  3. **source 归一**: `human`→`HUMAN`（词级等价大小写归一），`None`→`UNKNOWN`（不补猜）

### 7.3 T-WF-02 ID Chain Integrity — 7/7 PASS

- **当前真实闭环（10-02 后不得回退）**: outcomes 100/100 有 outcome_id；reviews 100/100 有 review_id 且 outcome 引用闭包 100%
- **断点清单（= Phase 0/1 目标）**:

| 断点 | 现状（实测） | 状态 |
|---|---|---|
| Thesis 无 thesis_id/scope/status | 2 张卡 0 命中（yaml 顶层键扫描） | 待修复（§1.2） |
| Decision 无 task_id | 19 条 0 命中（53 键全集无 task_id） | 待修复（§4.2） |
| Outcome 无 thesis_id | 100 条 0 命中 | 待修复（§2） |
| Signal 层缺失 | data/signals/ 不存在 | 待建设（Phase 1） |
| Task Events 缺失 | task_events.jsonl 不存在 | 待建设（Phase 0） |

### 7.4 偏差发现 → 约束固化（RED → GREEN 记录）

| ID | 发现 | 根因 | 修复（固化进测试/文档） |
|---|---|---|---|
| RED-01 | 首跑 2 断言失败: source 断言 `'human'` ≠ 契约大写枚举 | created_by 存量小写（13/19 None, 6 条 human）vs 契约大写 | normalize source 大写归一（词级等价, 非语义猜测） |
| RED-02 | 首跑 1 断言失败: COHR 卡误判含顶层 status | assumption 嵌套 `status: active` 被行扫描误认顶层 | yaml 扫描仅认无前导空格键 → 固化 "thesis status 必须顶层键" 约束 |
| 发现-01 | 路径漂移: outcomes/reviews 实际在 `data/ledger_historical/`（v0.2 §1.3 写 `data/ledger/`） | 勘察先行 | 测试按真实路径钉住（characterization 防文档漂移机制生效例证） |

### 7.5 验收结论（冻结）

```
Characterization Status:   GREEN (16/16 passed, 2026-09-03, 0.11s)
Schema compatibility:      CONFIRMED — v2 schema 可无损承接真实 19 条决策 + 100 条 outcome/review 链
Migration implementation: NOT STARTED（10-02 后）
Production mutation:      NONE（原文件不变断言通过）
```

**语义边界**: 本节证明的是"可以迁移"，不是"已经迁移"。10-02 后 migrate 脚本实现时，以 `tests/workflow/test_wf_01_decision_normalization.py` 内的 `MIGRATION_MAP` / `normalize_decision()` 为对齐契约（reference 实现，文件头已注明对齐义务）。

---

## 附录: 改动文件清单（Phase 0 全部落点）

| 文件 | 动作 |
|---|---|
| `growth_os/workflow/__init__.py` + `ids.py` + `events.py` | 新建（ID 生成 + 事件读写聚合） |
| `growth_os/ledger.py` | 修改 init_from_book（+3 字段，.get() 容错） |
| `tools/decision_cli.py` | 修改（+--queue/--add 入口，save 附加 3 可选字段） |
| `tools/migrate_decisions_v2.py` | 新建（normalized 视图生成 + 报告） |
| `tools/validate_thesis_v2.py` | 新建（thesis 卡结构 lint） |
| `data/thesis/*.yaml` × 2 | 修改（补 3 字段 + 注释） |
| `data/ledger/task_events.jsonl` | 新建（运行期产物） |
| `tests/workflow/test_wf_01_decision_normalization.py` | ✅ 已落地（2026-09-03, 9/9 GREEN） |
| `tests/workflow/test_wf_02_chain_integrity.py` | ✅ 已落地（2026-09-03, 7/7 GREEN） |
| `docs/RESEARCH_WORKFLOW_LAYER_V2_SCHEMA.md` | v0.2.1 勘误（signal_type→trigger_type） |
| **不改** | decisions.jsonl 原文件、overlay/*、outcomes/reviews.jsonl、--book/--stock/--quick 路径、L/E/P 逻辑 |

---

*Implementation Baseline v0.2。Schema 与测试边界已冻结（§7 证据）。10-02 后仅剩三个实施动作: ① migration 脚本 ② task/signal ID 接入 ③ CLI --queue 入口。不再增加 schema。*
