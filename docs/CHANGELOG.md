# CHANGELOG

## Sprint 19 — v2.5.0 (2026-05-31)

### 已修复

- **L1 排雷信号→仓位传导**: review verdict 标的自动降级（核心→标配, 标配→轻仓），消除"L1说谨慎/仓位说越跌越买"矛盾。影响: 焦点科技/三生国健/恺英网络/小商品城。
- **仓位双因子校验**: persistence≤2 封顶轻仓, price_cycle 封顶轻仓, L1 review 降一级。新易盛从标配→轻仓。
- **周期状态范式感知**: tech_penetration/brand_premium 标的不再误判为"周期顶部→警惕反转"。新增 STRUCTURAL_HIGH 状态（结构性高位,正常持有）。影响: 旭创/三生国健。

### 已知问题

| 优先级 | 问题 | 计划 |
|--------|------|------|
| P1 | tech_penetration 粒度不足（drug_ramp≠光模块） | Sprint 20 行业模板化 |
| P1 | share_gain 在装修装饰/商业物业行业误用 | Sprint 20 行业过滤器 |
| P2 | L3 Sigmoid 低 WACC 过度奖励 | Sprint 21 标注集30+后校准 |
| P2 | L2 费用率闸评分层未实现 | v4.0 架构 |
| P3 | quality_growth 驱动力待确认 | Sprint 20 行业判定分支 |
| P3 | L5 PEG 对 price_cycle 失效 | Sprint 20 光模块专用估值锚 |

### 路线图

| 版本 | 内容 | 准入条件 |
|------|------|---------|
| Sprint 20 | 行业模板化（光模块/游戏/医药/跨境电商/建筑装饰） | 静默期 2 周 |
| Sprint 21 | Growth Gene 拆分 + 多标签归因 | 标注集 ≥ 30 |
| v4.0 | L2 费用率闸 + L3 Sigmoid 架构级校准 | Sprint 20/21 数据验证 |

---

## Sprint 18 — v2.4.0 (2026-05-30)

### 已修复

- **分类器数据断层**: classify() 直接消费漏斗预计算字段(rd_ratio/roic_ttm/gross_margin_trend/debt_ratio)，不再手工拼 dict 重算
- **ASSET_HEAVY_L1 行业守卫**: capacity_expansion 仅重资产行业(电子/机械设备/化工等14个L1)触发，消除焦点科技/小商品城误判
- **quality_growth 后备类别**: 高ROIC+正增长未命中规则→quality_growth(置信度50%)，消除 unknown 标签
- **position.py 映射矛盾**: LABEL_CONFIG 替换 POSITION_MAP，weight/hold/action 由 MATRIX label 统一派生
- **funnel.py rd_ratio 预存 bug**: rd_intensity 补 "value" 键，修复 rd_ratio=None

---

## Sprint 17 — v2.3.0 (2026-05-29)

### 已修复

- **GM 标签子串匹配**: "上升(行业领先)" 等复合标签 → 子串匹配，消除精确匹配 bug
- **ROIC 波动率误伤科技成长**: 成长性豁免(rd>3%+CAGR>30%)，中际旭创从 price_cycle→tech_penetration
- **TTM ROIC 数据源**: Growth Source 优先使用漏斗 roic_ttm，消除单季/TTM 口径差异
