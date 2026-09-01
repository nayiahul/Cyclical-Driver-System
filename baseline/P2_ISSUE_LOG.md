# P2 Issue Log — 非阻塞问题登记

> 规则：Gate 0-D 冻结期间发现的 out-of-scope 问题一律登记，不混入 A baseline 归因。
> 修复必须独立 commit + 独立归因。

| ID | 发现日期 | 文件 | 问题 | 影响 | 修复计划 | 状态 |
|---|---|---|---|---|---|---|
| P2-001 | 2026-09-01 (Gate 0-A) | `valuation_filter.py::_load_price_data` | 价格源指向 `data/cache/daily_prices/`（当前为空目录），乖离率(规则3)与流动性(规则5)恒不触发 | 排雷层 2/8 条规则未生效，可能高估候选集质量（未量化） | Gate 3：迁移 `MarketData.as_of` 时统一数据源指向 `STOCKS_DIR`，并验证规则恢复后候选集/回测差异 | 待修复 |
| P2-002 | 2026-09-01 (Gate 0-A) | `signals.py::compute_S3/S4` | compute_alpha 路径存在 `iloc[-1]` 价格前视（PDR P0-1d），但未进入主回测 | 无当前影响；未来若启用 compute_alpha 路径则泄漏 | Gate 3：与 screener 一并迁移 `MarketData.as_of` | 待修复 |
| P2-003 | 2026-09-01 (Gate 0-D) | `growth_os/data.py` | 财务快照绕过 disclosure 治理（PDR P0-2） | Growth OS 路径前视 | Gate 4 | 待修复 |
| P2-004 | 2026-09-01 (Gate 0-A) | 价格数据覆盖 | F-1: 本地价格仅 2021+，2015-2020 无价格 | 回测窗口限制 2022-2025；旧结果不可复现 | P2 数据工程：2015-2021 补齐（独立立项） | 待评估 |
| P2-005 | 2026-09-01 (Gate 0-A) | `data/archive/` | L10: TDX 快照为最新值覆盖历史，数值可能被事后修订（第三类前视） | 因子数值可能被修订污染（未量化） | L10 Evidence Audit（Gate 4-6 后） | 待修复 |
| P2-006 | 2026-09-01 (Gate 0-A) | `sw_stock_industry.csv` | 行业映射为 2026-05 单时点快照（L2） | 历史行业分类不准确 | IndustryData.as_of 静态声明 + 3 年窗口限制 | 待修复 |
| P2-007 | 2026-09-01 (Gate 0-A) | 退市股 | 无 delist master + 退市股价格缺失（P0-3A） | 幸存者偏差 | Universe Data Spike → U1 | 待评估 |
| P2-008 | 2026-09-01 (Gate 0-A) | `output/` 旧结果 | 6/5 旧结果对应 commit `452b583^` 前代码 + akshare 在线价格 + 已删除的 daily_prices 缓存 | 不可复现，不能作为基准 | 标记 `INVALID_FOR_VALIDATION`，仅作历史参考 | 已归档 |

## 与 PDR 优先级映射

- P2-001 → 新发现（Gate 0-A）
- P2-002 → PDR P0-1d
- P2-003 → PDR P0-2
- P2-004 → F-1（新发现）
- P2-005 → PDR L10
- P2-006 → PDR L2
- P2-007 → PDR P0-3A
- P2-008 → 新发现（6/5 不可复现）
