# CHANGELOG — Cyclical-Driver-System

## v1.0 Research Layer（2026-09-02 冻结）

### 架构跃迁
- 量化选股程序 → PIT 可信研究系统 → Discovery 发现系统 → Lifecycle 状态机 → Research Allocation System

### 核心交付
| 模块 | 说明 |
|---|---|
| `pit/` | 数据可信层（Market/Financial/Universe/Industry + PITGuard） |
| `growth_os/state_machine.py` | L0-L5 状态机（行业范式参数化 v2） |
| `growth_os/l5_recovery.py` | 错杀恢复引擎（四层判定，恢复率 50.2%） |
| `growth_os/lifecycle_research.py` | 研究任务分配器（双雷达 + Research Card） |

### 实证结论
- 价格泄漏占旧收益 85%（A→A1 -112pp）
- L1 跨周期稳定（2022-2025 L1-L0 四年为正）
- L5 恢复率 50.2%（指标修正后），错误率 8.7%
- 状态迁移: L1→确认 46.3% / L3→L5 16.7% / L5→L3 25.1%

### 关键文档
- PDR_Remediation_Plan.md（完整方案）
- LIFECYCLE_MODEL_V1.md（状态机冻结版）
- RESEARCH_CARD_SCHEMA.md（输出格式）
- INVESTMENT_HYPOTHESIS.md（H0-H4 假设）
- DISCOVERY_AUDIT.md / L5_RECOVERY_V2.md / STATE_TRANSITION_MATRIX.md

### 纪律
- Lifecycle ≠ Score（标签不进评分）
- 先验证后接入（Train/Test 分离）
- 指标错误可判死模块（L5 26.7%→50.2% 教训）
