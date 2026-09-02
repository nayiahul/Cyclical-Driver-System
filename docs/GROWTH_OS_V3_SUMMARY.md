# Growth OS v3.0 — 项目总结（里程碑）

**日期**: 2026-09-02 | **状态**: 正式运行冻结期（Step 11：30 天真实运行验证）

---

## 一、项目目标

> 从 5000+ 股票池中，建立发现"变化、错杀、认知差"的 AI 辅助投研系统。

核心不是预测价格，而是：缩小研究范围、提高研究效率、保留判断过程、复盘学习。

## 二、演进路径（九阶段）

| Phase | 内容 | 关键成果 |
|---|---|---|
| 1 | PIT 数据可信层 | 85% 收益泄漏归因；财报披露治理 |
| 2 | Discovery Engine | 探针（合同负债/CAPEX/ROIC/毛利）；L1-L0 四年为正；Lead Time 4-9 个月 |
| 3 | Lifecycle L 状态机 | L0-L5；行业范式参数化 |
| 4 | **L5 Recovery** | 恢复率 50.2% / 错误率 8.7% / Eff 53%；**指标修正教训**（26.7%→50.2%） |
| 5 | 行业边界验证 | 三数据源失败 → **职责边界：公司自动化 + 行业人工**（徐工/融捷实证） |
| 6 | **Expectation E 引擎** | L1×E0/E1 升级率 53.2-53.9% vs 基线 47.5%；E2 陷阱区 15.3% |
| 7 | Research Allocation | Radar-Quota（修复 RPI 坍缩）；5000→2868→562→Top50 |
| 8 | Investment Memo | 七模块（Thesis/Broken/Action）；幻觉检查（每句可溯源） |
| 9 | Decision Ledger | 6+1 原型样本五类场景；历史回填演练 100 条；Evidence 保持率（CAPEX 88% > order 78% > margin 60%） |

## 三、最终架构

```
PIT → Discovery → Lifecycle(L) × Expectation(E) → Opportunity Matrix
→ Research Allocation → Research Book → Investment Memo
→ Human Decision → Outcome Ledger → Calibration
```

## 四、能力与边界

### 已验证
✅ 变化发现 ✅ 错杀识别 ✅ 认知差识别 ✅ 研究池压缩 ✅ 逻辑结构化 ✅ 判断留痕 ✅ 复盘框架

### 明确边界（系统不替代，归人工）
行业供需预测 / 产业链变化 / 政策判断 / 竞争格局——进入 Human Research Layer

## 五、方法论沉淀（贯穿全程的原则）

1. **先验证后接入**（假设→审计→Train/Test→小范围→升级）
2. **指标纪律**（评价函数错误可判死有效模块——L5 26.7%→50.2%）
3. **归因隔离**（每次只改一个变量；性能优化/数据修复/语义修复分 commit）
4. **不建综合评分**（RPI 两次失败；多正交状态 + 人工判断）
5. **负结果也是资产**（行业层三失败 → 职责边界确认）
6. **能力边界诚实声明**（Current State ≠ Forward Expectation）

## 六、运行期任务（Step 11，30 天）

```bash
python tools/run_research_scan.py           # 全市场研究池（~3min）
python tools/build_daily_research_book.py   # Top50 + Memo（~1min）
python tools/decision_cli.py --book output/research_book_{date}.csv --resume
```

- 目标: Decision Ledger 50 条 / Override ≥5 例 / 研究定位 ≤10 分钟
- T+90（2026-12-01）自动回填 → Calibration v2

## 七、不建议做（当前）

更多因子 / 综合评分 / 自动交易 / AI Agent / 更多行业 Layer——缺的是真实反馈数据，不是模型能力。

## 八、核心文档索引

| 文档 | 内容 |
|---|---|
| `GROWTH_OS_V3_FROZEN.md` | v3.0 冻结版 |
| `LIFECYCLE_V3_MODEL.md` | L/E 双轴模型 |
| `L5_BOUNDARY_REPORT.md` | 能力边界确认 |
| `EXPECTATION_AUDIT_V1.md` | E 引擎验证 |
| `CALIBRATION_PROTOTYPE_V1.md` | 校准原型 6 样本 |
| `L5_RECOVERY_V2.md` | L5 指标修正 |
| `PDR_Remediation_Plan.md` | PDR 全程方案 |
| `INVESTMENT_HYPOTHESIS.md` | 三引擎假设框架 |
