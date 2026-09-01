# Research System Architecture v1 — 研究系统架构基线

**状态**: 已冻结（2026-09-01）— 进入 Gate 4 前的架构决策
**背景**: 项目从"回测型选股程序"演变为"投资研究基础设施"。本架构定义未来形态，Gate 4 后按此演进，不在旧 Composite 上打补丁。

---

## 一、核心定位

> 从 5000 家公司中，可信地发现 20-50 家值得研究的公司，
> 并为每家提供"为什么进入 / 变化是什么 / 市场是否确认 / 估值如何 / 风险在哪 / 需要验证什么"。

成功标准（不是年化收益）:
1. **发现能力**: 5000 → 100 → 20 → 5 的压缩是否可信
2. **解释能力**: 每个候选都有完整证据链
3. **稳定性**: 研究池是否有持续性

## 二、目标架构（五层流水线）

```
5000 家公司
    │
    ▼
┌─────────────────────────────┐
│ Layer 0: 数据可信层 (pit/)   │  ← 已建设 (Gate 2)
│  MarketData / FinancialData  │
│  UniverseData / IndustryData │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Layer 1: Discovery Engine    │  ← 未来重点 (接口已定义, 未实现)
│  变化检测: 产业周期/盈利拐点/  │
│  订单/技术替代/资本开支       │
│  输出: DiscoveryResult(L0-L5)│
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Layer 2: Confirmation Engine │  ← 当前已有 (需因子有效性验证)
│  市场确认: RPS/行业强度/资金  │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Layer 3: Valuation Engine    │  ← 部分已有
│  估值: PE分位/PEG/同业比较   │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Layer 4: Research Memo Engine│  ← 未来建设
│  输出: 研究卡片 (不是 score) │
└─────────────────────────────┘
    │
    ▼
人工深度研究 → 投资决策 → 反馈闭环
```

## 三、当前代码 vs 目标架构（差距清单）

| 目标层 | 当前实现 | 差距 | 演进路径 |
|---|---|---|---|
| Layer 0 | ✅ pit/ + data_governance | Gate 4 财务 PIT 未完成 | Gate 4 → B |
| Layer 1 | ⬜ 仅接口 (pit/discovery_interface.py) | S1/S2 覆盖率 7%/20% 待查 | Phase 2 验证 H0/H1 后实现 |
| Layer 2 | 🟡 screener.compute_composite 内嵌 | 与 Discovery/Valuation 混合，无法单独验证 | Phase 2 Confirmation Audit 拆分 |
| Layer 3 | 🟡 同上（PE 分位内嵌） | 同上 | 同上 |
| Layer 4 | ⬜ 无（growth_os 归因卡片是雏形） | 需要"研究卡片"输出 | Phase 3 |

## 四、三个代码风险（已确认）与处置

### 风险 1：旧 Composite 是中心
- **现状**: `compute_composite()` 一个函数融合 RPS+S1+S2+S5+S7+PE，是排名唯一入口
- **风险**: 无法单独验证每个引擎贡献（A/B 对照只能看整体）
- **处置**: Phase 2 验证阶段**不重构**（避免归因污染）；验证完成后再拆 `compute_discovery()/compute_confirmation()/compute_valuation()`

### 风险 2：研究输出与交易输出混用
- **现状**: backtest/engine.py、screener.py、growth_os 共用因子，输出混在 output/
- **风险**: 研究池质量与组合表现无法分离评价
- **处置**: Phase 3 拆 `research/`（研究池生成）与 `backtest/`（假设验证），当前阶段保持（不改结构避免归因污染）

### 风险 3：Growth OS 定位未升级
- **现状**: growth_os/ 是"财务因子模块"（L1-L5 漏斗 + 评分）
- **目标**: 应成为 Discovery Engine 核心（企业变化检测系统）
- **处置**: Gate 4 修完其财务 PIT 后，Phase 3 升级为变化检测系统（生命周期 + 拐点 + 催化）

## 五、演进路线（更新）

```
A1 (运行中) → A/A1/B1 三版本归因
    ↓
Gate 4: growth_os 财务披露 PIT (P0-2) ← 当前
    ↓
B: 完整 PIT baseline
    ↓
Research Audit B: 财务泄漏影响 (S1/S2 是真弱还是被污染)
    ↓
Phase 2: 三引擎验证
  H0: 三引擎互补?  H1: 认知差?  H2: 周期拐点?  H3: 质量过滤?
    ↓
Phase 3: Discovery Engine 建设 + Research Memo + 反馈闭环
    ↓
AI Research Assistant
```

## 六、Gate 4 关注点（财务时间语义）

- 语义从 `report_date` 升级为 `available_date`（披露日）
- 验证 S1/S2 在 PIT 后：覆盖率是否变化（数据缺失 vs 定义过严 vs 真无价值）
- Growth OS 六层漏斗全面接入 FinancialData.as_of
