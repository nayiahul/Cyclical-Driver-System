# Lifecycle v3 Model — L/E 双轴研究状态机（设计冻结）

**日期**: 2026-09-02（Step 9-D1）
**依据**: Expectation Audit H-E1（L1×E0/E1 升级率 53.2-53.9% vs 基线 47.5%；L1×E2 陷阱 15.3%）
**核心架构变化**: L（企业状态）与 E（市场认知）是**两个正交维度，不合并为单状态**

---

## 一、双轴定义

### Axis 1: Lifecycle State（企业发生了什么）
| L | 含义 | 判定（不变） |
|---|---|---|
| L0 | 无变化 | Discovery 低 |
| L1 | 经营变化出现 | Discovery≥0.5 + RPS<40 |
| L2 | 市场开始确认 | Discovery≥0.5 + RPS 40-70 |
| L3 | 一致预期 | Discovery≥0.5 + RPS≥70 |
| L5 | 错杀恢复 | L5 引擎四层 |

### Axis 2: Expectation State（市场知道多少）
| E | 含义 | v0 代理（RPS） | v1 增强（成交额） |
|---|---|---|---|
| E0 | 市场忽略 | RPS<30 | + 成交额 Z<0 |
| E1 | 少数关注 | RPS 30-60 | + 成交 Z 上升 |
| E2 | 市场确认 | RPS≥60 | + 成交放大 |
| E3 | 一致预期 | RPS≥80 | — |
| E4/E5 | 透支 | 估值分位>90% | — |

## 二、Opportunity Matrix（研究优先级）

| L\E | E0 | E1 | E2 | E3+ |
|---|---|---|---|---|
| **L1** | **A+** ⭐ | **A** ⭐ | C ⚠️ | D ❌ |
| **L2** | A | **A/B** | C | D |
| **L3** | B | B | C | D |
| **L5** | **A** ⭐ | A | B ⚠️ | C |

```
核心修正:
  L1×E0/E1 → A 级（预期差窗口，实证 53% 升级率）
  L1×E2   → C 级（市场已定价，实证 15.3% 陷阱——修正 L1 一律 A）
  L5×E0   → A 级（恐慌+未坏，最佳错杀窗口）
  L5×E2   → B 级（恢复已部分交易）
```

## 三、原则（延续）

1. **L/E 不合并**——双标签并列输出（lifecycle_state + expectation_state）
2. **不进评分**——priority 由矩阵查表（研究任务分配），非权重
3. **E v0 用 RPS 代理，v1 加成交额**（已验证 RPS 代理就有 +6pp 增量）

## 四、验收标准（研究效率，非收益）

| 指标 | 旧 | 新目标 | 证据 |
|---|---|---|---|
| Opportunity Precision | L1 全部 47.5% | L1×E0/E1 >52% | ✅ 53.2-53.9% |
| Research Compression | L1 池 6107 | 缩小 30-50% | 待量化 |
| False Positive | L1×E2 混入 | 降级为 C | 待实现 |

## 五、实现拆分

```
Step 9-D2: growth_os/expectation_state.py
  classify_expectation(code, t_date) → {state: E0-E2, drivers, risks}
  （复用 MarketData RPS + volume/amount Z）

Step 9-D3: lifecycle_research.annotate() 扩展
  输出列: lifecycle_state + expectation_state + research_priority（矩阵）
  radar 不变（L 决定雷达，E 决定优先级）

Step 9-D4: 全市场扫描验证
  对比 v2: L1×E2 是否被降级 / 压缩率 / 升级率
```

## 六、暂缓（明确不做）

- 分析师预测接入（v0 代理已产生增量）
- AI 新闻/情绪（成本高，未验证增益）
- E 状态进评分（防 RPI 重演）

## 七、数据

- baseline/expectation_audit.csv（E 状态 + fwd6）
- baseline/expectation_transitions.csv（迁移）
