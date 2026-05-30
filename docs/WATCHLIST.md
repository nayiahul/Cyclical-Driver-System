# WATCHLIST — Sprint 19 静默实盘观察清单

版本: sprint-19-v2.5.0 | 日期: 2026-05-31
状态: 静默期（bugfix only，禁新 feature） | 预计复盘: 2026-06-14

---

## 静默期纪律

**允许**: 数据管道 bugfix、日志补全、观察清单更新
**禁止**: 评分逻辑修改、权重调整、Sigmoid 参数变更、L1 排雷规则修改、新 Growth Gene 分类

---

## 重点观察标的

### Tier 1 — 高优先级

**三生国健 (688336)** — drug_ramp vs tech_penetration
- 当前: tech_penetration | receivable_surge | 标配(4-8%) [review降级]
- 异常: 生物制品应收激增，drug_ramp 与光模块 tech_penetration 共用标签
- 观察: Q2 经营现金流、应收周转天数、扣非/营收剪刀差
- 阈值: Q2 现金流改善→维持；恶化→Sprint 20 receivable 细粒度联动

**郑中设计 (002811)** — project_cycle vs share_gain
- 当前: share_gain | 核心(8-15%) | 装修装饰
- 异常: 酒店装修项目周期驱动，非份额抢夺
- 观察: 新签合同增速 vs 营收增速、行业 CR5、毛利率可持续性
- 阈值: CR5 提升+GM稳→维持；项目周期特征明显→标签修正为 project_cycle

**小商品城 (600415)** — 商业物业 share_gain 适用性
- 当前: share_gain | 标配(4-8%) | rd=0.3%, 扣非/营收背离
- 异常: 商业物业"份额"来自线下流量迁移，非产品力
- 观察: 扣非/营收剪刀差、商铺出租率、OCF/净利润
- 阈值: 扣非追上营收→维持；持续背离→Sprint 20 降级+行业过滤器

### Tier 2 — 中优先级

**焦点科技 (002315)** — quality_growth 驱动力确认
- 当前: quality_growth(50%) | 标配 | 扣非-12%
- 观察: 费用率拆解、平台 GMV 增速
- 行动: Sprint 20 跨境电商增加 platform_expansion 分支

**恺英网络 (002517)** — 游戏 share_gain 研发不足
- 当前: share_gain | 标配 | rd=4.8%, 销售费用84%
- 观察: 新游流水占比、MAU、销售费用率环比
- 行动: Sprint 20 游戏模板用 deferred_revenue+MAU 替代纯财务指标

**新易盛 (300502)** — L5 PEG 对 price_cycle 失效
- 当前: price_cycle | 轻仓(<2%) | PEG=0.66 失效
- 观察: 800G/1.6T 订单能见度、ASP 变化、库存周转
- 行动: Sprint 20 光模块 price_cycle 专用估值锚(PB-ROE/EV)

---

## 系统性风险

| 风险点 | 观察窗口 | 触发条件 |
|--------|---------|---------|
| tech_penetration 过度集中(8/20) | 2周 | 板块回调 15%+ 且组合回撤>10% |
| share_gain 护城河未验证(8/20) | 2周 | 3+ 标的同周费用率恶化 |
| L3 Sigmoid 低 WACC 奖励过度 | 2周 | 低 WACC 标的超额收益偏离预期 |

---

## 复盘检查清单 (2026-06-14)

- [ ] 三生国健 Q2 现金流数据更新
- [ ] 郑中设计行业 CR5 数据获取
- [ ] 小商品城扣非/营收剪刀差收敛?
- [ ] 6 只观察标的中几只有行动需求
- [ ] 系统性风险项是否触发
- [ ] Sprint 20 行业模板优先级排序（光模块/游戏/医药/跨境电商/建筑装饰）
- [ ] 标注集是否达 25+ 例（距离 30 例还差多少）
- [ ] 静默期内是否出现新的 misclassification pattern
