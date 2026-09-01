# Expectation Engine Hypothesis — 预期引擎假设框架（研究设计 v0）

**状态**: 假设设计（2026-09-01）— **不进入代码实现**
**前置条件**: 五审计（OOS/Transition/LeadTime/WinnerCapture/FalsePositive）通过后，Lifecycle Engine 成立才启动
**定位**: 不是"预测市场预期"，而是"**估计市场已经知道多少**"

---

## 一、背景：Discovery ≠ 认知差

当前系统实际计算的是：

```
经营变化（Discovery）
    −
价格确认（RPS）
    =
企业变化发现（部分认知差）
```

完整认知差应该是：

```
企业真实变化（Reality）
    −
市场预期（Expectation）
    =
预期差（Mispricing）
```

**当前缺 Expectation 半边**——系统能发现"经营拐点"，但无法判断"市场是否已 price in"。

### 举例
| 公司 | 利润增长 | 市场预期 | 实际结果 |
|---|---|---|---|
| A | +50% | +60% | 低于预期 → 跌 |
| B | +20% | -10% | 超预期 → 重新定价 |

系统目前只看到左边两列，看不到"市场原来期待多少"。

## 二、当前能力边界

| 层 | 已有 | 缺失 |
|---|---|---|
| Reality（真实） | ✅ 财报/探针（订单/CAPEX/毛利） | — |
| Attention（关注） | 🟡 RPS（价格代理） | 融资余额/成交/研报关注 |
| Expectation（预期） | ❌ 无 | 盈利预测/预测修正 |
| Price（价格） | ✅ RPS/行业动量 | — |

## 三、三层架构（按成本递进）

### Level 1：Attention Proxy（最低成本，现有数据可做）
回答：**市场有没有开始注意？**

| 代理 | 数据 | 现状 |
|---|---|---|
| 融资余额变化 | `margin_data.csv`（2010 起，本地已有） | ✅ 可直接构建 `margin_change_20d/60d/acceleration` |
| 成交活跃度 | 价格文件 volume/amount 列 | ✅ 可构建 `turnover_zscore/volume_change` |
| RPS | 已有 | 重新定位为 Attention→Price 的最后阶段 |

### Level 2：Expectation Revision（需外部数据）
回答：**市场预期有没有改变？**

- 分析师盈利预测：`EPS_now vs EPS_3months_ago`，核心是**变化率**（revision），不是绝对值
- 来源候选：akshare `stock_research_report_em`（研报）、tushare Pro（需积分）
- 覆盖限制：2022 年前历史难获取

### Level 3：Consensus Gap（最终目标）
```
Expectation Gap = Reality − Consensus
```
实际增长 vs 一致预期的差 = 最有价值的信号。

## 四、可验证假设（H-E1/H-E2/H-E3）

### H-E1：关注度变化领先价格变化
- **预测**: 融资余额/成交放量先于 RPS 上升
- **数据**: margin_data + volume（本地已有）
- **验证**: Lead Time 同法（Attention 首次放量日 vs RPS 确认日）
- **失败标准**: 无稳定领先 → Attention 无增量

### H-E2：预期修正具有增量预测力
- **预测**: 盈利预测上调的股票，未来超额收益更高（控制 Discovery 后）
- **数据**: 分析师预测（需接入）
- **验证**: 预测修正分组 × fwd 收益（正交于 Discovery）
- **失败标准**: 无正交增量 → 不需要接预测数据

### H-E3：Reality × Expectation Gap 优于 Reality 单独
- **预测**: 高 Reality + 低 Expectation（预期差）最优
- **数据**: Reality（探针已有）+ Expectation（Level 1/2）
- **验证**:

| Reality | Expectation | 预期结果 |
|---|---|---|
| 高 | 低 | **最佳（预期差）** |
| 高 | 高 | 已 price in |
| 低 | 低 | 无机会 |

- **失败标准**: 对角线无差异 → 认知差框架不成立，维持现状

## 五、验收指标

| 假设 | 指标 | 阈值 |
|---|---|---|
| H-E1 | Attention 领先 RPS 的中位天数 | > 0 且领先比例 > 60% |
| H-E2 | 预测修正的 IC（控制 Discovery 后） | IC > 0.02 |
| H-E3 | 高Reality×低Expectation 组 fwd6 | 显著优于高Reality×高Expectation（>3pp） |

## 六、实施纪律（防止归因污染）

1. **当前阶段零代码**——不接数据、不改评分、不改 state_machine、不改 run_screen
2. 五审计完成 → Lifecycle Engine 判定 → 才启动 Expectation v0
3. v0 只做 H-E1（用现有数据，成本最低）→ 通过才评估 Level 2 数据接入
4. 每次只改一个变量（延续 PDR 的归因隔离原则）

## 七、研究演进路径（总览）

```
PIT → 可信数据          ✅ 完成
Discovery → 发现变化    ✅ 验证中（五审计）
Lifecycle → 判断阶段    ⏳ 五审计后判定
Expectation → 判断认知  📋 本文档（假设阶段）
AI Research Memo → 辅助决策  ⬜ 未开始
```

## 八、风险与限制

- 分析师数据 2022 前历史难获取 → Level 2/3 验证窗口受限
- 融资余额是 A 股特有的杠杆资金代理，可能与机构认知不同步
- 若 H-E1 失败：Attention 无增量 → 预期引擎降级为"仅 RPS 代理"，不再投入
- 若 H-E3 失败：认知差框架在 A 股不成立 → 系统定位为"企业变化发现系统"（仍有价值）
