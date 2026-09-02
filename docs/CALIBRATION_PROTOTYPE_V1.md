# Calibration Prototype v1 — 校准原型集（冻结）

**日期**: 2026-09-02
**状态**: 冻结——6 条 Decision Ledger 构成 Calibration Taxonomy 原型，停止人工采集，进入框架设计

---

## 一、样本库（6 条）

| # | 标的 | 类型 | 系统 | 人工 | 校准场景 |
|---|---|---|---|---|---|
| 1 | 300308 中际旭创 | MODEL_EXCEPTION | L0/IGNORE | DEEP/HIGH | A. 范式过滤盲区（tech_growth 误伤强信号） |
| 2 | 605499 东鹏饮料 | MODEL_CONFIRM | L5-A | DEEP/HIGH | B. L5 跨范式有效（消费） |
| 3 | 603486 科沃斯 | MODEL_MIXED | L5-A | WATCH/MED | C. 估值体系重估（成长→价值 PE 切换） |
| 4 | 000425 徐工机械 | MODEL_MIXED | L5-A | WATCH/MED | D. 周期恢复缺行业确认环 |
| 5 | 002192 融捷股份 | MODEL_DISAGREEMENT | L5-A | IGNORE/HIGH | E. 行业结构恶化（供给过剩→假错杀） |
| 6 | 地产链（行业级） | POLICY_EXCLUSION | — | IGNORE_ALL | F. 政策天花板行业排除 |

## 二、Calibration Taxonomy v1（分歧 → 缺陷层 → 改进方向）

| 分歧类型 | 暴露的系统缺陷 | 候选改进（Step 8 评估，不自动改） |
|---|---|---|
| A 范式盲区（300308） | tech_growth 全量 IGNORE 误伤强信号 | ALLOW_EXCEPTION 通道：AI 产业链/高壁垒制造/订单驱动型 |
| B 系统正确（605499） | 无（验证有效区） | 保留；加入长期跟踪确认恢复率 |
| C 估值重估（603486） | L5 不识别估值体系切换 | L5 v2 加"估值中枢"变量：成长→价值切换检测 |
| D 周期确认（000425） | L5 缺行业景气确认 | L5 v2 加 Cycle Turning 条件（行业 RPS/销量/价格数据） |
| E 结构恶化（002192） | 探针滞后于行业价格周期 | L5 v2 加 Industry Health 层（供给/需求/价格趋势） |
| F 政策天花板（地产链） | 无结构性对策（政策不可建模） | 行业黑名单机制（人工维护，政策变化时更新） |

## 三、核心发现（五条样本共同揭示）

> **L5 目前回答"企业有没有坏"，但五个分歧样本中四个（C/D/E）都指向同一缺口：缺少"行业维度"确认。**

```
L5 v1 = Business Intact + Market Damaged
L5 v2 候选 = Business Intact + Market Damaged + Industry Confirmation
              （Cycle Turning / Valuation Regime / Industry Health）
```

## 四、Step 8 原则（防主观覆盖）

1. **案例积累 → 形成假设 → 历史验证 → 小范围测试 → 版本升级**（不因单条人工判断改模型）
2. 人工分歧只产生"候选改进方向"，不直接改权重
3. 每个改进方向必须先在历史数据（2022-2025）验证，再进生产
4. T+90 真实结果回填后，与历史样本共同验证

## 五、后续采集策略

- 冻结主动采集（6 条已覆盖六类场景）
- 改为**按需补充**：发现新分歧类型才录（如人工发现系统未覆盖的场景）
- T+90（2026-12-01）自动回填所有 PENDING_VALIDATION 记录

## 六、数据

- `data/ledger/decisions.jsonl`（6 条，含 calibration_tags）
- 复跑: tools/decision_cli.py（按需补充新样本）
