# Golden Pit Review Template v1 — 黄金坑候选标准化审查模板

**版本**: v1（2026-09-03，从 COHR 真实案例固化）
**定位**: 黄金坑候选的标准化审查模板（非交易策略）
**来源**: COHR Golden Pit Review v1（系统第一份完整案例）
**用途**: AEHR / FORM / AMAT / ONON / 及其他标的复用，保证横向可比
**版本纪律**: v2 = 积累 10 案例后优化；v3 = 形成黄金坑数据库模板

---

# 0. Decision Gate（固定置顶 — 触发线状态先于分析）

```markdown
# Golden Pit Review

代码: 
公司: 
日期: 
当前价格:          ← ✅ 实时核验
触发条件:          ← 读 configs/{ticker}.yaml
状态: [ ] 未触发  [ ] 已触发  [ ] 已完成重评
52周区间 / 距高点 / 200日均线位置:
```

> 规则: 触发线命中（如 ≤300）→ 必须完成完整重评，禁止默认等待。

# 1. 核心判断摘要

```markdown
一句话判断:

这是: □基本面恶化 □周期调整 □估值压缩 □情绪错杀 □政策冲击 □真正黄金坑

当前状态:
企业价值: ↑ / → / ↓
市场价格: ↑ / → / ↓
安全边际: 扩大 / 不变 / 收缩
```

> 核心: 好公司 ≠ 好价格。安全边际 = 企业价值变化 − 市场价格变化。

# 2. 黄金坑十条件

| # | 条件 | 判断 | 证据 |
|---|---|---|---|
| 1 | 股价明显下跌 | | |
| 2 | 市场情绪悲观 | | |
| 3 | 基本面无永久恶化 | | |
| 4 | 长期产业逻辑成立 | | |
| 5 | 护城河稳定 | | |
| 6 | 现金流问题可解释且有修复路径 | | |
| 7 | 资产负债表安全 | | |
| 8 | 估值进入明显安全边际 | | |
| 9 | 修复催化明确 | | |
| 10 | 证伪风险可控 | | |

```
满足: X/10 → 结论: 未出现 / 接近 / 已出现
(条件8估值未满足时通常判定"接近"而非"已出现")
```

# 3. 企业价值检查（公司价值有没有下降？）

**商业模式**: 收入来源 / 客户结构 / 产品竞争力（有无结构性变化）
**护城河五项**: 技术壁垒 / 客户认证 / 成本优势 / 规模优势 / 生态位置
评级: ↑增强 / →不变 / ↓恶化
**关键**: 区分"周期受损"与"永久性损伤"（护城河下降=永久）

# 4. 财务质量

| 指标 | 趋势 | 备注 |
|---|---|---|
| Revenue | | |
| Gross Margin | | |
| Operating Margin | | |
| OCF | | |
| FCF | | ← 最高优先级: 利润是否变成现金 |
| CapEx | | ← 检查是否产生回报 (Incremental ROIC) |
| Inventory | | ← 危险信号: Revenue↑ 但 Inventory↑↑ |
| Net Debt | | |
| ROIC | | |

危险组合: Revenue/EPS↑ 但 Inventory↑↑ + CapEx↑↑ + OCF↓ + FCF长期负 → 提高风险评级

# 5. 市场错误类型（六分类）

```
主: 1基本面恐慌 2估值压缩 3周期底部 4政策冲击 5流动性踩踏 6技术路线恐慌
次: (可多个)
案例: COHR = 主2估值压缩 / 次6技术路线 + 4政策
```

# 6. Thesis Card（生成 data/thesis/{TICKER}_thesis_card.yaml）

```yaml
core_thesis:
  name:
  evidence: [...]
  counter_evidence: [...]

key_assumptions:
  - id: A1
    name: 
    status: active/watch   # watch = 需验证

falsify_conditions: [...]
x_monitors:
  policy: [...]
  industry: [...]
  company: [...]
```

# 7. Trigger State（生成 data/triggers/{TICKER}_trigger_state.yaml）

```yaml
price_trigger:
  condition: "price <= 300"
  status: triggered/not_triggered

next_triggers:
  - type: price_range / event
    range: 
    action: 
    check: [...]
```

# 8. 估值安全边际（禁止只给目标价）

回答:
1. 当前市场隐含什么假设?（Reverse DCF: 未来5年 Revenue CAGR / GM / FCF Margin 需多少才能支撑现价）
2. 该假设 vs 合理预期: 过于乐观 / 合理 / 保守
3. 参考锚: 自身历史 PE 区间 / 可比公司 / 周期底部估值
4. 结论: 便宜 / 合理 / 偏贵 / 极贵

# 9. 操作决策

```
已持仓: 加仓 / 持有 / 等待 / 减仓 / 退出
  理由(必须含: 价格+估值+基本面三要素, 非机械到线操作)

新资金: 不买 / 观察 / 试仓 / 分批买 / 重点买
```

# 10. 证伪条件（明确可检验）

```
如果发生: 1. 2. 3. → 投资逻辑失效
(必须写具体可观察条件: FCF持续负/毛利率跌破X%/指引下修/份额流失等)
```

# 11. 后续跟踪节点

```
下一财报: (重点验证 FCF/Inventory/NetDebt/GM)
下一事件: (如产品发布/政策节点)
重点验证: 
```

# 12. 归档规范

```
报告:    output/research/{ticker}_golden_pit_review_{date}.md
Thesis:  data/thesis/{TICKER}_thesis_card.yaml
Trigger: data/triggers/{TICKER}_trigger_state.yaml
决策:    data/decisions/{TICKER}_{date}.json (status: COMPLETED)
```

---

## 版本历史

| 版本 | 日期 | 依据 | 变更 |
|---|---|---|---|
| v1 | 2026-09-03 | COHR 案例 | 初版（Gate/十条件/错误类型/Thesis/Trigger/三条件卖出） |
| v2 | 待定 | 10 案例后 | 待优化 |
