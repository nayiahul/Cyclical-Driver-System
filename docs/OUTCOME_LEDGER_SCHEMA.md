# Research Outcome Ledger Schema v1 — 研究结果账本（数据模型冻结）

**状态**: Schema 冻结（2026-09-02）— **不实现代码，先锁定数据结构**
**定位**: 让系统知道"过去哪些判断正确/错误/为什么"——自我学习的基础层
**上游**: Daily Research Book（Top50 Memo，含 Evidence Trace）

---

## 一、三个核心对象

### 对象 1：ResearchOutcome（研究结果——自动回填）

```json
{
  "outcome_id": "RO-20260901-000425",
  "stock": "000425",
  "memo_date": "2026-09-01",
  "radar": "recovery_radar",
  "state_at_memo": "L5",
  "confidence": 0.8,

  "price_outcome": {
    "t30": null, "t90": null, "t180": null, "t365": null,
    "max_drawdown_90": null,
    "vs_industry_90": null
  },

  "state_transition": {
    "actual_path": null,       // 如 "L5→L2"
    "t90_state": null,         // 90 天后状态
    "t180_state": null
  },

  "thesis_outcome": {
    "revenue_confirmed": null,     // 收入兑现?
    "margin_confirmed": null,      // 毛利兑现?
    "order_confirmed": null,       // 订单兑现?
    "verdict": null                // "confirmed" | "partial" | "failed" | "pending"
  },

  "evidence_effectiveness": {
    "green_probes_at_memo": ["order", "capex"],
    "which_probes_held": null,     // 事后哪些探针仍为 green
    "which_probes_failed": null
  }
}
```

### 对象 2：InvestmentDecision（人工决策——研究员填写）

```json
{
  "decision_id": "ID-20260901-000425",
  "outcome_id": "RO-20260901-000425",
  "decision": "buy" | "watch" | "pass",
  "reason": "估值偏高，等待回调",
  "position_size": null,          // 如 5%
  "decision_date": "2026-09-02",
  "review_note": null
}
```

### 对象 3：ThesisReview（自动复盘——T+90 后生成）

```json
{
  "review_id": "TR-20260901-000425",
  "outcome_id": "RO-20260901-000425",
  "generated_at": "2026-12-01",
  "price_verdict": "positive",     // vs 行业超额
  "state_verdict": "recovered",    // L5→L2/L3?
  "thesis_verdict": "partial",

  "attribution": {
    "pe_repaired": true,           // 估值修复贡献
    "industry_improved": true,     // 行业改善贡献
    "fundamentals_held": true,     // 基本面兑现
    "evidence_led": ["order"]      // 哪个证据最有效
  },

  "learning": {
    "confidence_should_be": "0.9", // 校准: 原 0.8 vs 实际
    "probe_adjustment": null       // 探针权重调整建议
  }
}
```

---

## 二、五类必须记录的结果（对应 Schema 字段）

| # | 类型 | 字段 | 自动/人工 |
|---|---|---|---|
| 1 | Price Outcome | `price_outcome` | 自动（T+30/90/180/365） |
| 2 | Thesis Outcome | `thesis_outcome` | 自动（探针/财务复核） |
| 3 | State Transition | `state_transition` | 自动（重算状态机） |
| 4 | Evidence Effectiveness | `evidence_effectiveness` | 自动（事后聚合） |
| 5 | Human Decision | `investment_decision` | **人工**（研究员填写） |

## 三、回填时间线

```
Memo 生成 (T0)
  ├── T+30: 价格/状态回填
  ├── T+90: 完整 ThesisReview (价格+状态+证据)
  ├── T+180: 中期复核
  └── T+365: 年度复盘 + 证据有效性聚合
```

## 四、聚合输出（Evidence Effectiveness 报告）

```
100 个 L5 样本的 90 天结果:
  合同负债 green → 恢复率 65%
  CAPEX green   → 恢复率 52%
  PE 压缩       → 恢复率 48%
  → 未来权重自然调整（探针级校准）
```

## 五、设计原则

1. **Schema 先冻结，实现后置**——本文件是数据契约
2. **人工决策必须保留**——系统不做自动交易，研究员填写 decision 是闭环关键
3. **Evidence Trace 是连接点**——Memo 的 trace 字段直接映射到 `evidence_effectiveness`
4. **校准目标明确**：confidence 修正 + 探针权重调整建议（不自动改权重，只给建议）
5. **失败也是资产**：Thesis failed 样本进入 `attribution` 分析（为什么错）

## 六、与现有系统的接口

| 现有组件 | Ledger 接口 |
|---|---|
| `memo_engine.generate()` | 产出 `outcome_id` + evidence trace |
| `state_machine` | T+90 重算 → `state_transition` |
| `l5_recovery` / probes | T+90 重查 → `thesis_outcome` |
| `pit/market` | T+30/90/180/365 价格 → `price_outcome` |
| 研究员（人工） | 填写 `investment_decision` |

## 七、数据文件规划

```
data/ledger/
  outcomes.jsonl      # ResearchOutcome (自动追加)
  decisions.jsonl     # InvestmentDecision (人工追加)
  reviews.jsonl       # ThesisReview (T+90 自动生成)
  evidence_effectiveness.json  # 聚合报告 (季度)
```

---

*Schema v1 冻结完毕。下一步 Step 7-B（自动回填实现）需此文件作为数据契约。*
