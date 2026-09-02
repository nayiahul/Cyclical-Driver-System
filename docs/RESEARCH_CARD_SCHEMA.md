# Research Card Schema v1 — 研究卡片数据结构（冻结）

**状态**: v1.0（2026-09-02）
**定位**: 研究员看到的不是分数，是研究任务

---

## 一、输出字段

| 字段 | 类型 | 说明 |
|---|---|---|
| code | str | 6 位代码 |
| name | str | 股票名称 |
| research_stage | str | Early Discovery / Confirmation / Consensus / Recovery Watch / Ignore |
| research_priority | str | A / B / C / IGNORE |
| radar | str | growth_radar / recovery_radar / watch |
| drivers | str | 进入理由（探针标签，分号分隔） |
| risks | str | 风险（探针 red / 收入恶化 / 利润恶化） |
| lifecycle_state | str | 内部状态 L0/L1/L2/L3/L5（调试用） |

## 二、双雷达输出

### Growth Radar（寻找变化）
| 股票 | 状态 | 优先级 | 理由 |
|---|---|---|---|
| xxx | L1 Early Discovery | A | CAPEX 改善 + RPS 未确认 |
| xxx | L2 Confirmation | B | 盈利确认中 |

### Recovery Radar（寻找错杀）
| 股票 | 状态 | 优先级 | 理由 |
|---|---|---|---|
| xxx | L5 Recovery Watch | A | 历史强势 + 估值压缩 + 基本面未坏 |

## 三、研究简报格式（Daily Research Brief）

```
Growth Radar — A级关注
  公司A [L1 Early Discovery]
    为什么: 🟢 CAPEX效率改善 / 🟢 利润边际改善 / RPS尚未确认
    风险: 行业周期下行 / 订单持续性
    需要验证: 新订单持续性 / 行业景气

Recovery Radar — A级关注
  公司B [L5 Recovery Watch]
    逻辑: 过去强趋势 → 市场杀估值 → 盈利未破坏
    关键问题: 为什么跌？是否只是估值压缩？
```

## 四、与 Score 的关系（正交）

```
Score:    回答"公司质量如何"（现有 composite，不变）
Lifecycle:回答"现在处于什么投资阶段"（新增标签，不进 score）
```

**禁止**: Lifecycle 优先级加权进 composite（PDR 教训：无证据加权 = 幻觉回归）

## 五、Schema 测试（tests/pit/test_lifecycle_research.py）

- 状态标签映射 ✅
- annotate 加齐 6 列且保留原列 ✅
- radar 分组 ✅
