# EVENT_THESIS_MAPPING_PROTOCOL — 事件-假设映射协议（X 接口冻结）

**日期**: 2026-09-03
**状态**: 冻结 — XIS 的"事件 → 哪条投资假设受影响"轻量连接层
**原则**: 不评分、不自动降级。只回答"哪条 Thesis 需要人工检查"。

---

## 一、核心对象：Thesis Link（轻量，非新模块）

事件记录增加映射字段（复用现有 Ledger/事件库，不建大系统）：

```json
{
  "event_id": "EV-20260903-001",
  "company": "300308",
  "event": "FCC拟限制中国光模块进口",
  "event_type": "E15",           // 04 v3 E1-E18 体系
  "date": "2026-08-04",

  "affected_thesis": [
    {
      "thesis_id": "T300308-03",
      "name": "北美云厂商收入持续增长",
      "impact": "negative",       // 方向（非评分）
      "need_check": true,         // → 人工检查请求
      "check_questions": [
        "北美收入占比?",
        "海外产能比例与认证?",
        "FCC范围是'新机型'还是全面?"
      ]
    }
  ]
}
```

**输出不是"扣10分"**，而是 **"Thesis Risk Review Required"**（人工检查请求）。

## 二、映射规则（事件 → Thesis）

### 1. Thesis Card 来源（已有，不新建）
从 Ledger DEEP/WATCH 标的聚合（check_points/counter_thesis 已有 90% 内容）：
- core assumption ← Memo Thesis
- key evidence ← Evidence 探针
- **falsify conditions ← Ledger check_points**（300308 已有 6 项）

### 2. E1-E18 → Thesis 域映射表（v1）

| 事件类 | 常影响 Thesis 域 | 检查问题方向 |
|---|---|---|
| E1 财报异常 | 增长持续性 | 单季 vs 趋势 |
| E2 指引变化 | Forward EPS | 上修/下修幅度 |
| E3 盈利修正 | 一致预期 | 30/60/90日方向 |
| E4 大客户 | 需求确定性 | 收入敞口验证 |
| E5 订单 | 订单兑现 | 合同负债/Backlog |
| E7 价格 | 毛利/ASP | 成本传导 |
| E8 产能 | 供给扩张 | 利用率 |
| E15 政策 | 市场可及性 | 政策→订单→Revenue→EPS 穿透 |
| E16 治理 | 资产负债表健康 | 护城河 |
| E18 宏观 | 需求环境 | 穿透至 EPS |

### 3. 触发规则（轻量）

```
事件命中 Thesis 证伪条件关键词
  → 输出 "Thesis Risk Review Required"（加入 Book 该标的区域）
  → 人工（你）判断: 保持 / 降级 / 删除该 Thesis
  → Ledger 记录人工决定（可追溯）
```

**禁止**: 事件自动改 L/E/P、自动降优先级、自动触发 04 动作。

## 三、与 STOP-FUNDAMENTAL 的衔接（04 侧）

X 映射发现的"Thesis 风险"是 04 STOP-FUNDAMENTAL 的**输入检查项**：
```
X: Thesis Risk Review Required
 ↓ 人工确认风险真实
 ↓
04 侧: 对照 STOP-FUNDAMENTAL 清单
  (大订单取消/EPS下修/核心客户流失/产业逻辑证伪)
 ↓
触发 → 04 退出逻辑 (交易执行层动作, 非研究层)
```

**衔接点明确**: X 只负责"标记风险"，是否触发止损由 04 规则 + 人工决定。

## 四、数据存储（轻量扩展）

```
data/events/{date}_events.jsonl   ← 增加 affected_thesis 字段 (可选映射)
data/ledger/decisions.jsonl       ← Thesis 状态人工更新 (保持/降级/删除)
data/thesis/ (待建)               ← Thesis Card 聚合视图 (从 Ledger 生成)
```

## 五、验证指标（30 天）

1. **映射覆盖率**: 高风险事件(政策/制裁/诉讼)中, 多少能映射到研究池标的的 Thesis?
2. **提前量**: Thesis Risk 标记 → 实际基本面恶化 的提前天数
3. **误报率**: 标记后 Thesis 未恶化的比例（防过度敏感）

## 六、实施顺序（遵守冻结）

1. ✅ 本文档冻结
2. ⬜ event_scan 增加 E1-E18 分类映射（词库升级）
3. ⬜ 运行 30 天积累事件-Thesis 对 → T+30 决定是否需要影响模型
