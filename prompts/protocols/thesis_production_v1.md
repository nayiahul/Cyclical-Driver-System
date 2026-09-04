# Thesis 沉淀协议 v1 — 从每日判断到可监控假设

> 运行期人工协议（冻结期适用, 2026-09-04）。零代码——只规定人工行为与文档产出。
> 依据: RESEARCH_WORKFLOW_LAYER_V2_SCHEMA.md（Thesis = 逻辑/归因单位）+ 300308 Lite 卡先例。
> 核心: **Thesis 数量 = 事件系统传感器数量**。没有 thesis, 信息只是新闻。

## 1. 为什么存在

30 天运行期每天产生 3-5 条判断。若判断只留在 decisions.jsonl, 10-02 后 v2 Signal 桥没有可供匹配的 x_monitors——传感器数量为 2（300308/COHR）, 事件层再强也是空转。

判断数据 → thesis 卡的沉淀链, 是冻结期唯一能提升 Signal 桥价值上限的动作。

## 2. 触发规则（方向过滤, 防抓错人）

同一标的满足**任一**条件 → 进入沉淀候选:

- **累计 2+ 次非 IGNORE 判断**（WATCH / RESEARCH_REQUIRED / DEEP_RESEARCH 类, 跨日累计）
- 人工在研究中主动标记"值得持续跟踪"（300308 类例外）
- 已存在校准样本（CAL-*/RUNTIME-CAL-*）指向该标的——校准样本是 thesis 的天然前身

**方向过滤**: IGNORE/IGNORE_PENDING 类判断**不触发**——被否决标的是负例样本（归 Calibration/四象限）, 不是 thesis 原料。

**当前候选（2026-09-04 盘点）**:
- 600338 西藏珠峰: 3 条非 IGNORE 判断 + CAL-003-PENDING → ✅ 候选（本周五首次沉淀）
- 605499 东鹏饮料: RESEARCH_REQUIRED + MODEL_CONFIRM(卡) → 观察（等待二次非 IGNORE）
- 603486 科沃斯: MODEL_MIXED WATCH → 观察

## 3. 沉淀节奏

- **每周五批量 10 分钟**回看本周判断（~15-25 条）→ 沉淀 1-3 张
- 不做实时沉淀——判断时是前瞻视角, 沉淀需要回顾视角; 且不打断 decision_cli 30 秒流
- 日常判断照常, 沉淀是判断的副产品, 不增加判断时负担

## 4. 两级门槛（防 30 张空卡污染传感器阵列）

| 级别 | 要求 | 执行成本 | 用途 |
|---|---|---|---|
| **candidate** | core_question 一句话 + why_now 一句 + 触发证据 | ~2 分钟/张 | 记录意图, 进 data/thesis/ |
| **active** | falsify 可判定（字段+比较符+阈值+时间窗）+ monitors 指向具体数据源 | 研究推进时升级 | 10-02 后接 Signal 桥供料 |

- candidate → active 由人工在研究推进时升级, **不自动**
- 空泛卡（falsify="需求下降风险"级）禁止入 active——噪声传感器比没有更糟

## 5. 模板与落点

- 格式: **复用 `data/thesis/300308_shadow_lite.yaml`**（Shadow Thesis Lite 模板——文件头注明"运行期纪律: 非重点持仓不建完整 Card; 只记录核心假设与证伪"）, 不新建格式
- 落点: `data/thesis/{code}_{name}_lite.yaml`（同 300308 命名）
- 补 thesis_id/scope/status 三字段（v2 §1.1, 10-02 前手动标注, 格式: TH-YYYYMMDD-NNN / company / candidate）

## 6. 合并规则（一个标的的论点散落三处, 沉淀 = 合并）

沉淀时必须回查该标的全部分散记录并**引用**（不复制全文）:

1. `data/ledger/decisions.jsonl` → thesis/判断演化史
2. `data/calibration/CAL-*` → 已有假设结构（600338 的 H1/H2/H3 已存在, 直接引用）
3. `data/overlay/state.yaml` + `transitions.jsonl` → 人机状态叠加
4. 已有 thesis 卡（如 300308）→ 直接补字段升级, 不重复建

示例: 600338 卡 = core_question 引 CAL-003 三假设 + monitors（锌价/塔中盈利/锂进展）+ falsify（H3 触发线）, CAL-003 文件保持原位。

## 7. 退出机制

- candidate 30 天无升级且无新证据 → 标记 stale, 人工决定归档或删除
- active thesis 的 status 流转裁判 = T+90 ThesisReview verdict（v2 §7.1）: confirmed → 保留 monitors; failed → archived **且 monitors 停供料**（防死 thesis 白收事件）
- archived 卡移入 `data/thesis/archive/`（保留归因价值, 不删除）

## 8. 与 v2 衔接

- candidate 卡 = 10-02 后 thesis 目录化的原料（validate_thesis_v2.py 届时 lint 现有卡）
- monitors 字段即 v2 §4 Signal 注册表的输入——**现在写 monitors 就是在定义未来订阅**
- 本协议不改变任何 L/E/P 判断规则, 冻结期纪律兼容（纯文档+人工行为）

## 9. 本周行动（2026-09-05 前）

1. 周五判断留痕后, 沉淀第一张 candidate 卡: `data/thesis/600338_xizangzhufeng_lite.yaml`
2. 卡内 core_question 引 CAL-003 H1/H2/H3, monitors 定义锌价/塔中/锂三域
3. commit: 协议 + 新卡 + 当日 events（归档型, 同 09-03 先例）
