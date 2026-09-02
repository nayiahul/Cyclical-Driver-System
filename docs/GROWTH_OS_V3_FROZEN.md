# Growth OS v3.0 — 冻结版（运行期验证基线）

**冻结日期**: 2026-09-02
**状态**: 模型功能冻结——进入 Research Workflow Validation（Step 11，30 天运行期）

---

## 一、架构（L/E 双轴）

```
                  PIT 数据可信层
                       │
        ┌──────────────┴──────────────┐
        │                             │
   企业变化层 L                  市场认知层 E
   Lifecycle L0-L5              Expectation E0-E3
   (Discovery/探针/状态机)         (RPS+成交额代理)
        │                             │
        └──────────────┬──────────────┘
                       │
             Opportunity Matrix (L×E)
                       │
           Research Allocation (Growth/Recovery 双雷达)
                       │
                 Investment Memo
                       │
                 Decision Ledger
                       │
                 Outcome Review (T+30/90/180/365)
                       │
                    Calibration
```

## 二、已验证核心能力（实证基线）

| 能力 | 证据 | 状态 |
|---|---|---|
| PIT 数据可信 | 85% 收益泄漏归因 + 全部治理 | ✅ 正式 |
| Discovery 变化发现 | L1-L0 四年为正、Lead Time 4-9 个月 | ✅ 正式 |
| L5 错杀识别 | 恢复率 50.2%、错误率 8.7%、Eff 53% | ✅ 正式 |
| **Expectation 认知层** | **L1×E0/E1 升级率 53.2-53.9% vs 基线 47.5%（+6pp）** | ✅ 正式（v3 新增） |
| **L/E 双轴矩阵** | L1×E2 陷阱区 15.3% 被降级 | ✅ 正式（v3 新增） |
| 研究分配 | Radar-Quota 双雷达均衡（修复 RPI 坍缩） | ✅ 正式 |
| 人工前瞻 | 徐工/融捷分歧样本人工判断正确（职责边界） | ✅ 实证 |

## 三、边界（明确不做）

1. **行业前瞻自动预测**——三个数据源验证失败，归人工（Ledger 记录分歧）
2. **综合 Alpha Score**——RPI 两次失败，保持多正交状态 + 人工判断
3. **AI Agent**——缺 100-300 条真实判断记录，不急于建设
4. **分析师预期接入**——v0 代理已验证 +6pp，先跑通再评估

## 四、Step 11：Research Workflow Validation（30 天）

### 使用流程（每日 ~10 分钟）
```bash
# 1. 生成研究池（L/E 标注）
python tools/run_research_scan.py            # ~3 分钟全市场

# 2. 生成 Daily Research Book（Top50 + Memo）
python tools/build_daily_research_book.py    # ~1 分钟

# 3. 人工判断留痕（Top50 逐只）
python tools/decision_cli.py --book output/research_book_{date}.csv --resume
```

### 关键指标
| 指标 | 目标 |
|---|---|
| 研究时间 | 5000→50 定位 ≤10 分钟 |
| 人工 Override 记录 | 系统 A vs 人工 IGNORE / 系统 C vs 人工 DEEP（各 ≥5 例） |
| Decision Ledger | 人工判断 50 条 |
| T+90 回填 | 2026-12-01 自动复盘 |

### 决策规则参考（L/E 定位）
```
L1×E0/E1 → A 级：变化发生+市场忽略（预期差窗口）
L5×E0/E1 → A 级：错杀+恐慌（最佳窗口）
L1×E2   → C 级：市场已定价（勿追）
L5×E2   → B 级：恢复已部分交易
```

## 五、数据与版本

| 项 | 值 |
|---|---|
| 财务数据 | tdx_v20260901_q2（含 2026Q2 中报） |
| Ledger 人工样本 | 6 条（5 类场景 + 1 行业排除） |
| 历史回填复盘 | 100 条（confirmed 27/partial 53/failed 20） |
| 测试 | 29 passed |
| 输出 | output/research_book_20260901.md（v3） |

## 六、后续演进（全部依赖运行期数据）

```
30 天使用 → Decision 50 条 → T+90 回填
→ Calibration v2（证据可靠性报告）
→ Expectation E1.1（成交额 Z 已内置, 加单季 yoy 加速度）
→ AI Research Agent（先有数据后有 Agent）
```
