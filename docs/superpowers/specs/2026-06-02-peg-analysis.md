# PEG 指标分析：定义、作用、可靠性及优化方向

> 2026-06-02 与 ChatGPT 多轮讨论结论。记录 PEG 在 Growth OS 中的实际定位、已知问题和后续优化优先级。

---

## 一、PEG 的定义与计算

### 公式

```
PEG = PE_TTM / (g_proxy × 100)
```

其中 g_proxy 是**历史数据推导的前瞻增速代理变量**，不是分析师一致预期。

### g_proxy 计算流程（`compute_forward_growth()`）

1. **指数加权 YoY**：近 4 季营收增速，权重 0.55 递减
2. **合同负债交叉验证**：合同负债增速作为先行指标，上修 g
3. **OCF 含金量折扣**：OCF/利润 < 0.75 → g × 0.7
4. **前瞻修正**：近 2 季 YoY 连续环比回落 → g 衰减
5. **回退**：数据不足 → 3 年 CAGR → 5% 地板值

g 强制夹在 4%-80% 区间。

### 与机构 PEG 的区别

| 维度 | 机构 PEG | 当前项目 PEG |
|------|----------|-------------|
| 分子 | Forward PE | PE TTM |
| 分母 | 分析师一致预期 EPS Growth | 历史营收 YoY 外推 |
| 数据源 | Bloomberg/Wind 一致预期 | TDX 财务数据 |

---

## 二、在系统中的作用

### 定位：L5 预期差校正因子，不是估值模型

```
L1 Risk ──┐
L2 Moat ──┤
L3 Efficiency ──┼──→ Composite (100%)
L4 Industry ──┤
L5 Expectations ──┘
                │
                ├── PEG (0-4分, 占L5的40%)
                ├── PE分位 (占L5的60%)
                └── L5本身占 Composite ~10%
```

**PEG 对 Composite 的影响 < 4%。** 不决定入选与否，只微调排序。

### PEG 评分表

| PEG 范围 | 评分 | 标签 |
|----------|------|------|
| < 0.5 | 4.0 | 低估 |
| 0.5-1.0 | 2.5 | 合理 |
| 1.0-2.0 | 1.0 | 偏贵 |
| > 2.0 | 0 | 高估 |

### 多层防护

| 防护层 | 机制 |
|--------|------|
| g_trusted 检查 | g* 与实际增速偏离 > 30pp 或符号相反 → 评分降为 1.0，打 ⚠️ |
| 成熟期折扣 | `PEG_CONFIDENCE` 按行业三级分类，caution → ×0.7, misleading → ×0.3 |
| 适用域限制 | 非加速期行业自动降低 PEG 权重 |

---

## 三、已知问题

### 问题 1：Revenue Growth ≠ EPS Growth

**风险**：增收不增利的公司（如焦点科技：营收 +15.6%，扣非 -12%），PEG 用营收增速会低估估值风险。

**当前防护**：L1 层已拦截（`deducted_vs_revenue` → review → 仓位降级）。但 PEG 计算本身不感知扣非利润质量。

### 问题 2：不同 Gene 的 PEG 有效性差异巨大

| Gene | PEG 有效性 | 原因 |
|------|-----------|------|
| tech_penetration | 高 | 营收增长≈利润增长≈估值扩张 |
| import_substitution | 较高 | 国产替代逻辑下增长有持续性 |
| platform_network | 中 | 边际成本递减，但增速可能波动 |
| share_gain | 中低 | 份额抢夺伴随费用率压力 |
| drug_ramp | 低 | 估值看峰值销售额/管线，不看过往增速 |
| hit_game | 极低 | 今年+100%，明年-50%，PEG 完全误导 |
| project_cycle | 无意义 | 项目制周期股，PE 和增速都不可比 |

**典型案例**：恺英网络 PE~10x，营收 +64%，PEG=0.16 看起来史诗级低估。实际上市场担心的是"下一款爆款在哪"，不是今年增速。

### 问题 3：质量保护缺失

当前 `compute_forward_growth()` 只看营收 YoY 和 OCF，不看扣非利润增速。当 `deducted_profit_yoy < revenue_yoy * 0.5` 时，PEG 信号可能严重失真。

---

## 四、优化方向（按优先级）

### P2：g_proxy 扣非收敛

```python
if deducted_profit_yoy < revenue_yoy * 0.5:
    g_proxy = blend(revenue_yoy, deducted_profit_yoy)
```

**不做理由**：影响全市场 4452 只标的的 L5 评分，需完整的回归测试。等标注集 30+ 后再动。

### P2：Gene-aware PEG 权重

| Gene | PEG 权重 |
|------|---------|
| tech_penetration | 100% |
| import_substitution | 80% |
| platform_network | 70% |
| share_gain | 60% |
| drug_ramp | 40% |
| hit_game | 20% |
| project_cycle | 0% |

**不做理由**：PEG 影响 <4%，Gene-aware 精细化收益太小。等 P0 完成后再考虑。

### P3：分析师一致预期接入

用 Wind/Bloomberg EPS 一致预期替代历史外推。

**不做理由**：需要付费数据源。当前数据基础设施不支持。

---

## 五、结论

1. **PEG 保留现有逻辑，无需改动。** 多层防护已覆盖主要风险。
2. **当前 P0 是 quality_growth 收缩和标注集扩充**，不是估值精度。
3. **扣非收敛和 Gene-aware PEG 是 P2 级别的精细化任务**，等系统核心稳定性验证后再做。
4. **PEG 最值得监控的不是准确性，而是它在 quality_growth 标的上的误导风险**——当 quality_growth 占比上升时，PEG 信号的可靠性会同步下降。
