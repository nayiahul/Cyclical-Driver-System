# Growth OS — 个人 AI 投研操作系统（v3.5 Shadow）

从 5000+ A 股中，发现"变化、错杀、认知差"，生成**研究任务**（非买入信号），
并通过 Decision Ledger 积累**可复盘的判断记忆**。

> 这不是选股模型，是研究资源分配器：系统做公司级筛选，人工做行业前瞻判断，
> 每次判断都被记录、回填、校准。

---

## 系统架构（L/E/P 三轴，v3.5）

```
PIT 数据层（披露日治理 + as_of 截断，零未来函数）
    ↓
Discovery（探针：订单/CAPEX/毛利/ROIC）
    ↓
Lifecycle L（L0-L5 企业变化阶段）
    ↓
Expectation E（E0-E3 市场认知程度）
    ↓
Paradigm P（AI_OPTICAL_CYCLE，Shadow only，只观察不决策）
    ↓
Opportunity Matrix（L×E → 研究优先级）
    ↓
Research Book（Top50 + 双雷达 + Memo 七模块）
    ↓
Decision Ledger（人工判断留痕）→ Outcome Review → Calibration
```

## 实证基线（全部经过历史验证）

| 能力 | 证据 |
|---|---|
| PIT 数据可信 | 85% 历史收益泄漏归因；财报披露日治理 |
| 认知差窗口 | L1×E0/E1 升级率 53.2-53.9% vs 基线 47.5%（+6pp） |
| 错杀识别 L5 | 恢复率 50.2% / 错误率 8.7% / Recovery Efficiency 53% |
| AI 光模块范式 | 61 次压制样本 fwd6 +36.4%（市场 5 倍）；反事实验证有效 |
| 职责边界 | 行业前瞻归人工（徐工/融捷分歧实证：人工判断正确） |

## 每日运行（~10 分钟）

```bash
source .venv/bin/activate

# 1. 全市场研究池（~3 min）→ output/research_pool_*.csv
python tools/run_research_scan.py

# 2. 研究书 Top50 + P Shadow 观察区（~1 min）→ output/research_book_*.md
python tools/build_daily_research_book.py

# 3. 判断留痕 3-5 只（质量 > 数量）→ data/ledger/decisions.jsonl
python tools/decision_cli.py --book output/research_book_YYYYMMDD.csv --resume
```

**决策纪律**：每天 3-5 个高价值判断 → 30 天 ~100 条有效样本 → T+30 Review（2026-10-02）。

## 研究书输出示例

```
Growth Radar（变化发生 + 市场未确认）: L1×E0/E1 → A 级
Recovery Radar（错杀恢复）:           L5×E0/E1 → A 级

每份 Memo 七模块:
  1 Identity（L/E/P 状态）  2 Why Now（企业侧+市场侧）
  3 Thesis（Bull/Base/Bear） 4 Evidence（可溯源）
  5 Catalyst（已知事件）     6 Thesis Broken（证伪条件）
  7 Research Action + 置信度
```

## 项目结构

```
pit/                    # 数据可信层（MarketData/FinancialData/Universe/Industry/PITGuard）
growth_os/
├── state_machine.py    # Lifecycle L 状态机（行业范式参数化）
├── expectation_state.py # Expectation E 状态（RPS+成交额代理）
├── l5_recovery.py      # L5 错杀恢复引擎（四层判定）
├── paradigm_shadow.py  # P 层 Shadow（AI_OPTICAL_CYCLE，只观察）
├── lifecycle_research.py # L/E 双轴标注 + Opportunity Matrix
├── memo_engine.py      # Investment Memo（七模块，每句可溯源）
├── ledger.py           # Outcome Ledger（T+30/90/180/365 回填）
└── growth_probes.py    # 探针（订单领先/CAPEX效率/毛利韧性/客户集中）
screener.py             # 历史轻量扫描器（保留）
backtest/               # 历史回测引擎（用于假设验证，非交易）
tools/
├── run_research_scan.py        # 每日全市场扫描
├── build_daily_research_book.py # 研究书生成
├── decision_cli.py             # 判断留痕 CLI
└── *.py                        # 审计工具（L5/Expectation/P层 全链可复跑）
data/
├── ledger/             # 人工判断（decisions.jsonl）
├── ledger_historical/  # 历史回填复盘（100 条）
└── cache/              # 数据缓存（gitignore）
docs/                   # 55 份研究文档（设计/验证/边界/版本）
tests/                  # 29 测试（characterization + PIT + schema）
```

## 核心方法论（演进沉淀）

1. **先验证后接入**：每个新能力走 7 步验证链（假设→候选→历史→子类→人工→反事实→Shadow）
2. **指标纪律**：评价函数错误可判死有效模型（L5 恢复率 26.7%→50.2% 修正）
3. **不建综合评分**：多正交状态（L/E/P）+ 人工判断，拒绝 `score = Σ w·factor`
4. **负结果即资产**：行业层三数据源失败 → 确认"行业前瞻归人工"边界
5. **防污染**：P 层 Shadow only——不改变 L/E 决策，30 天观察后才转正

## 版本状态

| 版本 | 状态 |
|---|---|
| v3.0 L/E 双轴 | ✅ Production |
| v3.5 Shadow（P 层观察期） | ✅ 运行中（2026-09-02 ~ 10-02） |
| v4.0 L/E/P 三轴 | ⏳ 待 T+30 Review 决策 |

## 核心文档索引

| 文档 | 内容 |
|---|---|
| `docs/GROWTH_OS_V35_RUNTIME.md` | 运行期冻结 + 每日清单 + 观察指标 |
| `docs/GROWTH_OS_V3_SUMMARY.md` | 九阶段演进总结 |
| `docs/PARADIGM_LAYER_V0_SPEC.md` | P 层设计规范（防污染四禁令） |
| `docs/LIFECYCLE_V3_MODEL.md` | L/E 双轴模型 |
| `docs/EXPECTATION_AUDIT_V1.md` | E 引擎验证（+6pp） |
| `docs/L5_BOUNDARY_REPORT.md` | 能力边界确认 |
| `docs/CALIBRATION_PROTOTYPE_V1.md` | 校准原型（6 样本） |
| `docs/PDR_Remediation_Plan.md` | PDR 全程（数据可信修复） |

## 历史模块（保留供参考）

- `screener.py` / `signals.py`（S1-S7）/ `backtest/` —— 演化前的因子/回测体系，
  现在用于假设验证而非交易决策。PDR 证明其历史收益 85% 来自未来函数泄漏，
  修复后真实年化 2.9%——**研究系统定位由此确立**。

## 数据说明

- 财务：TDX（`~/Downloads/tdxfin`，当前 2026Q2 中报，披露日治理）
- 行情：akshare 腾讯源（2021+，as_of 截断）
- 行业：SW 静态映射 + 行业指数日线（8 个关键行业）
- 新鲜度：行情 T-1，财务为最新已披露报告期
