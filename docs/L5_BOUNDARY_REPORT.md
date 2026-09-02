# L5 Recovery Boundary Report v1 — 能力边界确认

**日期**: 2026-09-02
**状态**: 冻结——L5 能力边界实证确认，行业层自动探索终止

---

## 一、已验证能力（L5 v1 正式能力）

| 能力 | 证据 |
|---|---|
| 公司级错杀识别 | 恢复率 50.2%（Train 50% / Test 51%）、错误率 8.7%、Recovery Efficiency 53% |
| 跨范式基本有效 | 消费（东鹏型）/ 周期制造（徐工型）均通过 |
| 历史回填稳健 | 2025-2026 演练：Recovery 状态恢复率 84% |

**定义**: L5 捕捉"市场已悲观 + 公司经营质量未同步恶化"——**公司层错误定价检测**，不是行业拐点预测。

## 二、未实现能力（三个数据源验证失败）

| 尝试 | 结果 | 失败本质 |
|---|---|---|
| 行业财务中位数（Step 8.2） | H1❌ H2❌ RED 组为空 | 财务滞后 2-4 季度 |
| 商品价格动量 LC0（8.4-A） | 融捷分歧时价格在涨（3M +26.4%） | 价格是同步变量，非前瞻 |
| 行业指数动量 SW（8.4-B1） | H1❌（DOWN 反而略高） | 指数是结果变量（市场怎么看） |

**共同本质**: 三者都是 Current State Data；人工分歧全部来自 Forward Expectation（未来供给/需求结构）。**静态数据无法预测行业结构性转折。**

## 三、职责边界（Machine/Human Split）

```
                Research System
                    |
    ──────────────────────────────
    |                           |
 Machine Layer             Human Layer
    |                           |
 公司状态识别              行业未来判断
 探针/财务/状态机         供需/竞争/政策/技术替代
    |                           |
 L5 Recovery             Industry Thesis
    |
 是否值得研究（公司级）
```

**分工原则**:
- 系统做: 公司级筛选（5000 → 50）+ 状态识别 + 研究优先级
- 人工做: 行业级前瞻判断（L5 候选的行业风险标签）
- Ledger 记录分歧 → 未来校准"人工优先检查"类别

## 四、L5 v2 修正（不再加 Industry Gate）

```
L5 v1（不变）
    ↓
输出 Recovery Candidate + Industry Uncertainty Flag:
  徐工型: L5-A + Cycle_Check_Required
  融捷型: L5-A + Supply_Risk_Check_Required
  科沃斯型: L5-A + Valuation_Regime_Check_Required
    ↓
Flag 驱动: Memo 的"人工验证项"（Research Action），非自动降级
```

## 五、Calibration Prototype 更新（人工判断前瞻性验证）

| 样本 | 系统 | 人工 | 结果（fwd6 回填） | 人工前瞻判断 |
|---|---|---|---|---|
| 000425 徐工 | L5-A | WATCH/MED（疑需求） | **-4%**（未恢复） | ✅ 谨慎正确 |
| 002192 融捷 | L5-A | IGNORE/HIGH（疑供给） | **-16%**（未恢复） | ✅ 强烈正确 |

**人工前瞻判断在两个分歧样本上均优于系统当前状态信号**——验证职责边界合理。

## 六、结论

1. L5 v1 维持正式能力；行业层自动探索**终止**（三个数据源 ROI 低）
2. 系统与人工的职责边界**实证确认**：公司级自动化 + 行业级人工
3. 下一步: Expectation Engine（市场预期变化——真正的缺口）

## 七、数据

- baseline/cycle_turning_audit.csv（1212 行）
- baseline/industry_context_audit.csv（1539 行）
- data/cache/lc0_lithium.csv + sw_index_*.csv（8 行业）
