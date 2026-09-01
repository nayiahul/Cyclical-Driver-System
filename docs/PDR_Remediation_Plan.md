# PDR Remediation Plan — Point-in-Time Integrity 修复方案

**状态**: 已拍板，执行中（Gate 0-D Pre-PIT Baseline 生成中）
**依据**: `Cyclical-Driver-System 完整 PDR 评审.txt`（NO-GO 结论）+ 源码复核 + 数据勘察
**拍板结论**: D1–D9 全部确认（详见 §1.4）；项目定位校准：AI 增强型投研工作台（2026-09-01 方向确认）
**日期**: 2026-09（勘察基准）

---

## 1. Executive Summary

### 1.1 结论

PDR 判定 v4.0 准入 NO-GO 成立。本次源码复核确认了 PDR 的核心指控（价格前视、财报前视、Universe 非 PIT），并新增发现一个 PDR **未覆盖**的更底层事实：

> **F-1（新增）: 本地价格数据仅覆盖 2021-01 至今。**
> `~/Desktop/stocks/`（实际价格源，`config/params.py:STOCKS_DIR`）共 5227 个文件，最小日期分布：4427 只从 2021-01-04 起、345 只 2022、236 只 2023、其余 2024-2026。**没有任何股票有 2021 年之前的价格数据**；`data/cache/daily_prices/` 为空目录。
>
> 推论：
> 1. `main.py` 的 2015–2024 回测在当前数据下**无法进行**（2015–2020 无价格 → 空仓现金）；
> 2. 历史结果（年化 73.41% / Calmar 3.26 / 回撤 -22.52%，记录于 `docs/ARCHITECTURE.md` 与 `docs/v1.0-baseline-reset-memo.md`）对应的数据版本**已不可复现**（Desktop/stocks 已被 2021+ 数据覆盖）；
> 3. 当前数据可支持的最大可信回测窗口 = **2022-01 ~ 2025-12**（与 `run_slice4.py` / `run_slice5.py` 一致）。

因此本方案对已拍板路线做**唯一实质修正**：

> **Gate 0 / Gate 7 的回测窗口从"2015–2024"调整为"2022–2025"（数据可用窗口）。**
> 2015–2021 历史价格补齐列为独立 P2 数据工程任务（§9.4），与 Phase 1 并行评估，不阻塞。

### 1.2 修复范围（Phase 1）

只修时间完整性，**零策略语义变更**（因子、权重、TopN、Regime、调仓时序全部原样）：

| 目标 | 范围 |
|---|---|
| P0-1 市场数据前视 | screener.py + valuation_filter.py + signals.py（S3/S4）→ `MarketData.as_of()` |
| P0-2 财务数据前视 | growth_os/data.py → `FinancialData.as_of()`（复用 data_governance 治理层） |
| P0-3A Universe 幸存者偏差 | 数据源 spike 先行（§9），不阻塞 Phase 1 |
| P1 三个 bug | 全部推迟到 Gate 9（Baseline v1 建立后）单独修 |

### 1.3 关键设计原则

1. **契约先行，逐模块迁移**：先建 `pit/` 数据访问边界，再修违规调用；效果级 guard 先行，机制级 lint 后置。
2. **归因隔离**：每一类变更单独 commit、单独回测、单独 attribution（A→B1→B→C 分层，§12）。
3. **旧结果不删除**：标记 `INVALID_FOR_VALIDATION`，作为 pre-PIT 对照基线。
4. **Future = HARD ERROR，Missing = UNAVAILABLE**：禁止静默 fallback 到未来/当前数据（§5）。
5. **Coverage 是 Gate**：修复不得引入隐性选择偏差（§7）。

### 1.4 已拍板决策（D1–D9）

| 决策 | 结论 |
|---|---|
| D1 | Phase 1 不含任何 P1 修复；P1-3 定性为 **bug**（commit 定义 `TTM ROIC = sum(单季OP×0.75)/平均IC`，`de_cumulate_series` 定义为还原单季度值，无负值 floor 说明；`q if q>0 else 0` 与自身数学定义冲突），Gate 9 单独修 |
| D2 | Universe PIT 分级 U0–U3，spike 不阻塞 Phase 1 |
| D3 | 新建 `pit/` 包作为唯一时间访问边界；`data_governance.py` 保留为 Financial PIT policy，由 `FinancialData.as_of()` 复用 |
| D4 | `as_of(t)` = 截至 t 日收盘已公开可得的数据（闭区间）；文档明确区分 observation_time / execution_time；当前 engine 时序（月末前一交易日观察、次月首交易日执行）保持不变 |
| D5 | future→HARD ERROR / missing→UNAVAILABLE / fallback to future→FORBIDDEN / prior-known fallback 仅语义明确允许时（§5）；新增 Coverage Audit（§7） |
| D6 | 双层防复发：Phase 1 效果级 PITGuard；Gate 10 机制级 architecture/lint guard（不禁止已 slice 后 DataFrame 上的 `.iloc[-1]`） |
| D7 | 立即冻结 pre-PIT baseline（任何代码修改前），含完整 manifest（§11 Gate 0） |
| D8 | pytest 引入；Characterization（初始 GREEN）+ Remediation（初始 RED）两类测试 |
| D9 | Data Lineage：PIT Provider 审计模式返回 value/source/source_date/effective_date/as_of 元数据 |

### 1.5 数据勘察新增事实（PDR 未覆盖）

| ID | 事实 | 影响 |
|---|---|---|
| F-1 | 价格数据仅覆盖 2021+（§1.1） | 回测窗口调整为 2022–2025；2015–2021 为独立数据工程任务 |
| F-2 | `data/archive/` 已存在历史财务快照（`tdx_financials_20260521_0801.csv` 等） | D7 manifest 与 L10 数值修订审计有现成基础 |
| F-3 | L10 已识别"第三类前视"：TDX 快照为最新值覆盖历史，数值可能被事后修订 | Phase 1 只做披露日正确性；数值修订列为 P2 量化任务 |
| F-4 | 价格文件含 `isST` 与 `tradestatus` 列 | U2（历史 ST）与 U3（停牌）的数据源可能现成，spike 需验证 |
| F-5 | 行业映射 `sw_stock_industry.csv` 为 2026-05 单时点快照（L2） | `IndustryData.as_of()` 返回静态映射并显式声明限制 |
| F-6 | `v1.0-baseline-reset-memo.md` 证实财务前视曾于 2026-05-18 修复过一轮（B1，法定截止日方案），但 **Growth OS 数据层未纳入**（P0-2 根因） | P0-2 修复是"补上漏网的接入点"，非新设计 |

---

## 2. 问题矩阵 P0/P1/P2

> 行号基于 2026-09 勘察时的代码，执行时以实际为准。

### P0 — 阻断级（Phase 1）

| ID | 文件 | 函数 / 位置 | 问题 | 根因 | 修复 | 验收测试 |
|---|---|---|---|---|---|---|
| P0-1a | `screener.py` | `compute_rps60` L51、`compute_industry_momentum` L89、`compute_theme_rps` L136 | `close.iloc[-1]` 取全量文件最后一行（= 本地最新日期），未按 t_date 截断 → 历史日期的 RPS/行业动量含未来价格 | 无统一 as-of 边界 | `MarketData.as_of()` | T-MKT-01 |
| P0-1b | `screener.py` | `compute_composite` L268、L313 | PE 计算 `df_price["close"].iloc[-1]` 同上；财务侧 L247 已正确走 `filter_available_reports`，价格侧泄漏 | 同上 | 同上 | T-MKT-01 |
| P0-1c | `valuation_filter.py` | L93-94（乖离率 MA200）、L158（流动性） | 同上，完整行情直接 `iloc[-1]` | 同上 | 同上 | T-MKT-01 |
| P0-1d | `signals.py` | `compute_S3` L80-113、`compute_S4` L166-184 | 同上（当前 `compute_alpha` 路径未进主回测，但泄漏存在；契约层就绪后一并迁移，成本为零） | 同上 | 同上 | T-MKT-01 |
| P0-2a | `growth_os/data.py` | `get_financial_snapshot` L45-52 | 仅 `report_date_str <= t_date`，未走披露日治理 → 报告期 2026-03-31、公告 2026-04-25 的数据在 2026-04-01 即"可见" | 未接入 `data_governance.filter_available_reports`（F-6） | `FinancialData.as_of()`（内部复用治理层） | T-FIN-01 |
| P0-2b | `growth_os/data.py` | `get_quarterly_series` L61-76 | 同上 | 同上 | 同上 | T-FIN-01 |
| P0-3A | `universe.py` + 数据 | `get_universe` L158 | 仅按 `list_date <= t_date` + 当前名称 ST 过滤；无 delist 数据、无历史 ST（PDR 确认）；**且退市股无价格文件（F-1 延伸）** | 缺 Historical Security Master + 退市股日线 | 数据源 spike → U1（§9） | T-UNI-01 |

### P1 — 高优先级（Gate 9 单独修）

| ID | 文件 | 位置 | 问题 | 根因 | 修复 | 验收测试 |
|---|---|---|---|---|---|---|
| BUG-001 | `growth_os/scorecard.py` | L281 | `card.roic_ttm = roic_wacc.get("roic") if roic_wacc.get("roic_ttm") else None` — 写入的是 `roic` 而非 `roic_ttm` | 字段语义 bug | 修字段 | T-BUG-01 |
| BUG-002 | `growth_os/data.py` | `de_cumulate_series` L182 | `q if q>0 else 0` 将负单季经营利润压 0，系统性抬高 TTM NOPAT/ROIC（已定性为 bug，D1） | helper 与自身定义冲突 | 保留符号 | T-BUG-02 |
| BUG-003 | `growth_os/run_screen.py` | L148/165 vs L255 | 决策阶段读 `_persist_map.get(code, 3)` 时 persistence 尚未写入（写入在 L255 Growth Source 分类后）→ 低持续性标的的"深度复核"判定用默认值 | phase ordering | classify 前置 | T-BUG-03 |

### P2 — 后续（不阻塞 PIT Baseline v1）

| ID | 内容 | 归属 |
|---|---|---|
| P2-1 | 2015–2021 历史价格补齐（F-1） | 数据工程，§9.4 并行评估 |
| P2-2 | L10 财务数值修订污染量化（F-3） | 抽样 10-20 家对比历史快照（archive 已有基础） |
| P2-3 | 行业映射非 PIT（F-5 / L2） | IndustryData 静态声明，3 年窗口限制 |
| P2-4 | 停牌/涨跌停执行约束（L3/L4） | U3（isST/tradestatus 列验证后） |
| P2-5 | 复权方式一致性（L6，待确认） | 数据审计 |
| P2-6 | Growth OS 回测 Calmar 非连续 NAV | Gate 11 收敛时统一 |
| P2-7 | 双系统/三套 Regime 漂移 | Gate 11 |
| P2-8 | 文档漂移（ARCHITECTURE v2.0 / STATUS v2.5 / PDR v3.0） | Gate 11 或随时 |

---

## 3. PIT Contract

### 3.1 时间语义（D4）

```
observation_time: 信号计算时点。当前 = 调仓日前一交易日收盘（get_t_date(day)）
execution_time:   交易执行时点。当前 = 调仓日（每月首个交易日）收盘
as_of(t) = 截至 t 日收盘已公开、已可得的数据（闭区间，含 t 日）
```

- Phase 1 不改 engine 时序；契约文档锁死该约定，防止后人误用 t 日信号做 t 日开盘交易。
- 未来若引入盘中信号/次日开盘执行，只需改 execution 语义，observation 契约不变。

### 3.2 Provider 接口（D3）

```
raw adapters (CSV/TDX/AKShare)  →  PIT Providers  →  domain logic
        data/cache/*                 pit/*            signals/screener/growth_os/backtest
```

```python
# pit/market.py
class MarketData:
    def as_of(self, code: str, t_date: str) -> pd.DataFrame
        # 返回 date <= t_date 的全部行情行；违规(数据源最小日期 > t_date) → UNAVAILABLE
    def close_on_or_before(self, code: str, t_date: str) -> float | None
        # 执行价查询（prior-known fallback，白名单语义，见 §5）
    def effective_date(self, code: str, t_date: str) -> str | None
        # 实际最后可得日期（供 guard / coverage / lineage）
    def coverage(self, codes: list[str], t_date: str) -> dict
        # {code: bool} 价格可用性（供 Coverage Audit）

# pit/financial.py
class FinancialData:
    def as_of(self, code: str, t_date: str) -> dict | None
        # 最新财务快照；disclosure_cutoff <= t_date 才可用（复用 data_governance）
    def quarterly_series(self, code: str, field: str, t_date: str, n: int) -> pd.Series
    def disclosure_info(self, code: str, report_period: str) -> dict
        # {report_period, disclosure_date, cutoff_source: actual|statutory}

# pit/universe.py
class UniverseData:
    def as_of(self, t_date: str) -> pd.DataFrame
        # U0: list_date <= t_date 且非当前名称 ST；U1+: 且 (delist_date is None or delist_date > t_date)
    def membership(self, code: str, t_date: str) -> str
        # "listed" | "delisted" | "not_yet" | "unknown"

# pit/industry.py
class IndustryData:
    def as_of(self, code: str, t_date: str) -> str | None
        # U0: 返回静态快照并携带 as_of_limitation 标记（F-5）

# pit/guard.py
class PITGuard:
    # 上下文管理器：记录 (module, code, requested_as_of, actual_effective_date)
    # 任意 actual > requested → raise PITViolation (HARD ERROR)
```

### 3.3 硬不变量（任何违反 → RAISE，不 fallback）

```
market:     max(price.date)  <= t_date
financial:  max(disclosure_cutoff) <= t_date
universe:   list_date <= t_date 且 (delist_date is None or delist_date > t_date)
industry:   静态快照（Phase 1 显式声明，不假装 PIT）
```

---

## 4. Data Lineage Contract（D9）

审计/调试模式下，PIT Provider 返回带元数据的数据结构（生产路径可剥离元数据以保性能）：

```json
{
  "value": 37.2,
  "field": "revenue_yoy",
  "report_period": "2020-03-31",
  "disclosure_date": "2020-04-28",
  "cutoff_source": "actual",           // actual | statutory
  "requested_as_of": "2020-04-30",
  "source": "TDX",
  "data_extract_date": "2026-05-21",   // F-3: 数值版本
  "code": "000001"
}
```

用途：
- 因子审计（Gate 12）可回答"这只股票为什么在 2020-06-30 得 83.2 分，用了哪份数据"；
- L10 数值修订审计（P2-2）依赖 `data_extract_date` 与 `data/archive/` 历史快照；
- 每次回测输出 `lineage_manifest.json`（全量或抽样）。

---

## 5. Missing / Future 行为矩阵（D5）

| 场景 | 行为 | 说明 |
|---|---|---|
| 请求 as_of(t)，数据源返回日期 > t | **HARD ERROR**（`PITViolation`） | 未来数据绝不可用 |
| 请求 as_of(t)，历史数据不存在（如 2017 财务缺失） | **UNAVAILABLE** → 模块级策略 + coverage 记录 | 见下方模块策略表 |
| fallback 到当前/未来数据补历史缺失 | **FORBIDDEN** | 静态 guard 拦截 |
| fallback 到 prior known data（如 `_get_close_price` 取 ≤ date 最近价） | **允许，需白名单登记** | 语义明确（执行价查询），显式记录 |

### 模块级 UNAVAILABLE 策略

| 模块 | 数据缺失时行为 | 现状 → 目标 |
|---|---|---|
| 财务指标（S1/S2/S5/S7/PE） | NaN → gate 排除 | 现状如此，保持；增加 coverage 统计 |
| 行情缺失（某调仓日无价格） | 该票跳过买入；持仓保留（engine 已有"无有效价格保留持仓"逻辑 L236-240） | 保持 |
| Universe 成员资格未知（退市股未收录） | U0: 不出现；U1+: 按 delist_date 排除 | U1 修复 |
| 行业映射缺失 | "未知"行业桶，不参与行业分位 | 保持，覆盖审计 |

---

## 6. 测试矩阵（D8）

### 6.1 测试分类

| 类别 | 目的 | 初始状态 | 最终状态 |
|---|---|---|---|
| **Characterization** | 锁死 Phase 1 不改变的策略语义（调仓时序/TopN/权重/成本/Regime/行业约束） | **GREEN**（必须一开始就绿） | 始终 GREEN |
| **Remediation** | 复现 PIT bug | **RED** | GREEN（Gate 6） |

### 6.2 测试清单

| ID | 类别 | 名称 | 验证内容 |
|---|---|---|---|
| T-MKT-01 | Remediation | Market PIT | 构造 t=2022-06-30 价格 10 / 2026-06-01 价格 100；`MarketData.as_of` 与全链指标只能见 10 |
| T-FIN-01 | Remediation | Disclosure PIT | report 2022-03-31 / disclosure 2022-04-25：as_of(2022-04-01) → UNAVAILABLE；as_of(2022-04-25) → available |
| T-UNI-01 | Remediation | Universe PIT | 上市 2010 / 退市 2020：Universe(2018) 含，Universe(2022) 不含 |
| T-GRD-01 | Remediation | No-Future-Access Guard | 回测运行中记录 requested vs actual，任何 actual > requested → fail |
| T-DET-01 | Remediation | Deterministic Backtest | 同 commit + 同 data manifest → NAV/trades/positions/因子分完全一致 |
| T-STA-01 | Remediation | 静态 guard（Gate 10） | 业务模块不得直接 `pd.read_csv(raw cache)` / import raw adapter；白名单 `pit/` + tools；**不禁止**已 slice DataFrame 上的 `.iloc[-1]/.tail(1)/.max()` |
| T-CHR-01..N | Characterization | 策略语义锁 | 调仓日序列、TopN=100、等权+8%上限、成本 0.3%、Regime 状态机、行业约束、PE 分位 |
| T-BUG-01..03 | Remediation（Gate 9） | P1 单测 | roic_ttm 字段 / 负 OP 保留符号 / persistence 顺序 |

### 6.3 工程要求

- 引入 pytest，`tests/` 目录；`conftest.py` 提供固定数据快照 fixture（不依赖网络）；
- T-DET-01 需要 manifest 机制（§11 Gate 0）；
- 测试数据用构造样本（3-5 只股票 + 合成日期），不依赖全量 5000 只。

---

## 7. Coverage Audit 设计（D5 强化）

### 7.1 每调仓日漏斗

```
Universe → Market data OK → Financial data OK → Industry OK → Eligible → Scored → Selected
```

每个截面输出 `coverage_{t_date}.csv` + 年度汇总表：

| 年份 | Universe | 有价格 | 有财务 | 完整评分 | 入选 |
|---|---|---|---|---|---|
| 2022 | 4800 | 96% | 90% | 85% | 100 |
| ... | | | | | |

### 7.2 分组维度

按年份 × 市值十分位 × 行业 × 上市年限交叉统计，防止 missing 造成隐性选择偏差（如"小盘财务缺失率 40%"导致系统变相成为大盘过滤器）。

### 7.3 Gate 规则

- Gate 5 建立 coverage 基线（post-PIT）；
- 此后任何数据/代码变更导致某分组 coverage 迁移 > ±5pp：必须解释，否则不得进入下一 Gate；
- UNAVAILABLE 原因编码（`no_price` / `no_financial` / `no_industry` / `delisted` / `suspended`）随 coverage 输出。

---

## 8. 文件/函数级修改映射

> 原则：每个 Gate 只产生一类变更；Gate 3/4 期间除 PIT 截断外零语义改动。

### Gate 2 — 新建 `pit/` 包（新文件，无既有代码改动）

```
pit/__init__.py      # 导出 4 个 Provider + PITGuard + PITViolation
pit/market.py        # MarketData（复用 signals._load_price_data 的缓存思路，增加 as_of 截断+断言）
pit/financial.py     # FinancialData（内部调用 data_governance.filter_available_reports / _load_calendar）
pit/universe.py      # UniverseData（U0 先行；U1 依赖 spike 结果）
pit/industry.py      # IndustryData（静态快照 + limitation 标记）
pit/guard.py         # PITGuard + PITViolation
tests/conftest.py    # 固定数据 fixture
tests/characterization/  # T-CHR-*
tests/pit/               # T-MKT-01 / T-FIN-01 / T-UNI-01 / T-GRD-01 / T-DET-01
```

### Gate 3 — 市场数据迁移（P0-1，只改读取，不改计算逻辑）

| 文件 | 函数 | 改动 |
|---|---|---|
| `screener.py` | `compute_rps60` L44-51 | `close = MarketData.as_of(code, t_date)["close"]`；删除 `iloc[-1]` 全量读取 |
| `screener.py` | `compute_industry_momentum` L82-89 | 同上 |
| `screener.py` | `compute_theme_rps` L129-136 | 同上 |
| `screener.py` | `compute_composite` L246-268、L312-313 | PE 价格侧改 `as_of` 截断；财务侧保持现状 |
| `valuation_filter.py` | L93-94（乖离率）、L158（流动性） | 同上 |
| `signals.py` | `compute_S3` L80-113、`compute_S4` L166-184 | 同上（compute_alpha 路径一并迁移） |

### Gate 4 — 财务数据迁移（P0-2）

| 文件 | 函数 | 改动 |
|---|---|---|
| `growth_os/data.py` | `get_financial_snapshot` L45-52 | `df[df["report_date_str"] <= t_date]` → `filter_available_reports(df, t_date)`（或经 `FinancialData.as_of`） |
| `growth_os/data.py` | `get_quarterly_series` L61-76 | 同上 |

### Gate 9 — P1 修复（独立 commit × 3）

| 文件 | 位置 | 改动 |
|---|---|---|
| `growth_os/scorecard.py` | L281 | `card.roic_ttm = roic_wacc.get("roic_ttm")` |
| `growth_os/data.py` | `de_cumulate_series` L182 | 保留符号（负值季度真实计入 TTM） |
| `growth_os/run_screen.py` | L148/165/255 | persistence 分类前置到决策之前 |

### Gate 10 — 机制级 guard

- `tests/pit/test_static_guard.py`：扫描业务模块（screener/signals/valuation_filter/growth_os/backtest/regime）的 raw cache 直接读取与 raw adapter import；
- 已确认正确截断的读取点（如 regime 指数、国债、融资余额等）登记白名单，不全量重写（D6：不为架构洁癖扩大修复面）。

---

## 9. Universe Data Spike 方案与分级验收（D2）

### 9.1 Spike 目标（只回答 4 个问题，不承诺产出）

```
Q1 能否得到历史全部 A 股 security master（含退市）？
Q2 能否得到 list_date + delist_date 完整映射？
Q3 能否得到退市股退市前完整日线（2015–2025）？
Q4 数据覆盖率（按年 × 交易所 × 退市原因分组）？
```

### 9.2 候选数据源（按优先序）

| 源 | 已知情况 | 验证点 |
|---|---|---|
| 通达信全证券日线（tdx.com.cn 官方"上证/深证所有证券日线"） | 官方提供全证券日线入口；PDR 曾提"深市退市股 API 返回空"（akshare 接口，非通达信） | Q1-Q4 |
| baostock | 免费，含退市股历史，覆盖 2015+ | Q1-Q3 |
| akshare `stock_info_*_delist` | 沪市可、深市空（memo L1/L8：沪市 151 只已获取） | 仅 Q1 部分 |
| tushare | 需积分 | 备选 |

### 9.3 分级验收（Universe PIT 成熟度）

| 级别 | 定义 | 验收 | 状态 |
|---|---|---|---|
| **U0** | 当前上市股 reconstructed universe | list_date <= t 且当前名称非 ST | Phase 1 起点（明确声明存在幸存者偏差） |
| **U1** | + list_date + delist_date | `Universe(2018)` 含退市股、`Universe(2022)` 不含（T-UNI-01）；退市股价格入库 | spike 通过后 |
| **U2** | + 历史 ST/风险警示 | 价格文件 `isST` 列质量验证（F-4）；构造 T-UNI-02（历史某日该股应被 ST 排除） | 依赖 F-4 验证 |
| **U3** | + 停牌/涨跌停/可交易 | `tradestatus` 列验证 + 执行约束接入（P2-4） | 远期 |

> 能到哪一级就明确标记哪一级；U2/U3 不阻塞 PIT Baseline v1。

### 9.4 2015–2021 价格补齐（P2-1，并行评估）

- 范围：当前上市股 5227 只 × 2015-01~2020-12 日线（~1500 交易日）；
- 源：akshare 腾讯源（与现有一致）或通达信全证券日线；
- 退市股缺口：依赖 spike 结果；
- 决策点：补齐后回测窗口可扩展回 2015–2024，届时 PIT Baseline 需重跑（窗口扩展属于数据变更，单独 attribution）。

---

## 10. Gate 0 → v4.0 完整实施顺序

```
Gate 0   冻结 PRE-PIT Baseline（立即执行，任何代码修改前）
   │
Gate 1   测试基建：pytest + Characterization(GREEN) + PIT Remediation(RED)
   │
Gate 2   PIT Contract v1：pit/ 包（MarketData/FinancialData/UniverseData/IndustryData/PITGuard）
   │      ├────── 并行：Universe Data Spike（§9）
   │
Gate 3   修 Market Leakage（screener + valuation_filter + signals S3/S4）
   │      └── 中间基线 B1（price-only fix）
   │
Gate 4   修 Financial Leakage（growth_os/data.py）
   │
Gate 5   Coverage Audit 基线建立
   │
Gate 6   PIT Tests 全 GREEN + Characterization 仍 GREEN
   │
Gate 7   完全同参数重跑（2022-2025 数据可用窗口）→ PIT-Corrected Baseline v1
   │
Gate 8   PRE vs POST Leakage Attribution（§12）
   │
Gate 9   逐项修 P1（独立 commit + 独立测试 + 独立 attribution）→ Baseline v2
   │
Gate 10  机制级 architecture/lint guard（T-STA-01）
   │
Gate 11  Canonical Pipeline 收敛（双系统合一，Gate 11 起才允许）
   │
Gate 12  完整 Factor Audit（IC/IR/Decay/VIF/Quantile/Ablation/Regime-conditioned）
   │
Gate 13  Regime / Execution Stress Test（2015 股灾/2018 熊市/2020 疫情/2024 春节；停牌/涨跌停）
   │
Gate 14  Walk-forward / Out-of-Sample
   │
v4.0
```

---

## 11. 每个 Gate 的 Entry / Exit Criteria

### Gate 0 — 冻结 PRE-PIT Baseline

- **Entry**: 无（立即执行）
- **Exit**:
  1. git tag `pre-pit-remediation`；
  2. 重跑 `run_slice4.py` + `run_slice5.py`（2022-2025，当前数据可支持窗口）并归档完整 Baseline Artifact：
     ```
     baseline/pre_pit/
       manifest.json      # baseline_id, commit_sha, tag, python/dep 版本, params hash,
                          # 每个输入文件 path/sha256/rows/min_date/max_date, 运行命令, timestamp
       params.json
       nav.csv / trades.csv
       run.log
       README.md          # 状态: INVALID_FOR_VALIDATION（原因: P0-1/P0-2/P0-3 未修 + F-1 数据不可复现）
     ```
  3. 输出统计存档（年化/回撤/Calmar/换手率）；
  4. 历史文档数字标注 `INVALID_FOR_VALIDATION`（ARCHITECTURE.md、v1.0-baseline-reset-memo.md 加注，不删除）。
- **注意**: 不跑 `main.py`（2015-2024 在当前数据下无意义，F-1）。

### Gate 1 — 测试基建

- **Entry**: Gate 0 Exit
- **Exit**: pytest 可运行；`pytest tests/characterization -m "not xfail"` 全绿；`pytest tests/pit` 中 T-MKT-01/T-FIN-01/T-UNI-01 在现代码下 RED（证明测试真的在测 bug）。

### Gate 2 — PIT Contract v1

- **Entry**: Gate 1 Exit
- **Exit**: `pit/` 包完成；T-MKT-01/T-FIN-01 对 `MarketData.as_of`/`FinancialData.as_of` 直接调用转 GREEN（此时业务模块尚未迁移）；PITGuard 单测通过；契约文档（§3/§4/§5）落盘。

### Gate 3 — 修 Market Leakage

- **Entry**: Gate 2 Exit
- **Exit**: screener/valuation_filter/signals 全部经 `MarketData.as_of` 取价；`grep` 确认主路径无未截断 `iloc[-1]`；中间基线 B1 存档（price-only fix，用于价格泄漏归因）。
- **验收测试**: T-MKT-01（业务级，非仅 Provider 级）转 GREEN。

### Gate 4 — 修 Financial Leakage

- **Entry**: Gate 3 Exit
- **Exit**: growth_os/data.py 两函数接入治理层；T-FIN-01 业务级 GREEN；P0-2 关闭。

### Gate 5 — Coverage Audit 基线

- **Entry**: Gate 4 Exit
- **Exit**: 2022-2025 全部调仓日 coverage 漏斗输出；年度汇总表；UNAVAILABLE 原因编码生效；与 Gate 0 的 coverage 对比报告（量化修复导致的 coverage 迁移）。

### Gate 6 — 测试全绿

- **Entry**: Gate 5 Exit
- **Exit**: 全部 Remediation Tests GREEN；全部 Characterization Tests 仍 GREEN；T-GRD-01 在 2022-2025 全量回测中通过（全程无 future access）。

### Gate 7 — PIT-Corrected Baseline v1

- **Entry**: Gate 6 Exit
- **Exit**: 完全同参数重跑 slice4/slice5 窗口；`baseline/pit_v1/` 归档（同 Gate 0 格式 + lineage manifest）；状态 `VALID_FOR_VALIDATION`（窗口内）。

### Gate 8 — Leakage Attribution

- **Entry**: Gate 7 Exit
- **Exit**: §12 归因报告（A/B1/B 三组对照表 + 结论）。

### Gate 9 — P1 修复（×3 独立 commit）

- **Entry**: Gate 8 Exit
- **Exit**: BUG-001..003 各独立 commit + T-BUG-* 单测 + 各自重新回测 attribution；`baseline/pit_v2/` 归档；P1 全部关闭。

### Gate 10 — 机制级 guard

- **Entry**: Gate 9 Exit
- **Exit**: T-STA-01 生效；剩余 raw 读取点登记白名单（含理由）；新代码准入规则写入 CLAUDE.md/docs。

### Gate 11 — Canonical Pipeline 收敛

- **Entry**: Gate 10 Exit，且 PIT 数据层稳定运行 ≥ 1 个完整版本周期
- **Exit**: 单一 Engine（Quick/Deep/Backtest/Report 四视图）；screener/growth_os 不再自实现第二套计算逻辑；三套 Regime 归一；文档与代码同步（P2-8 关闭）。

### Gate 12 — Factor Audit

- **Entry**: Gate 11 Exit
- **Exit**: S1/S2/S3/S4/S5/S7 × 1M/3M/6M/12M × BULL/STRUCT/BEAR 的 IC 均值/IC std/IR/Decay/VIF 报告；对照附件标准（IR≥0.3 因子≥4 个、std(IC)≤0.15、VIF≤3、6 个月 IC 仍为正）逐项判定。

### Gate 13 — Regime / Execution Stress Test

- **Entry**: Gate 12 Exit
- **Exit**: 2015 股灾/2018 熊市/2020 疫情/2024 春节四场景 DEFENSE 触发验证（快速通道延迟 ≤1 交易日）；最大回撤 ≤35% 验证（连续 NAV）；停牌/涨跌停执行约束（依赖 U3）。

### Gate 14 — Walk-forward / OOS

- **Entry**: Gate 13 Exit
- **Exit**: 滚动训练/测试协议报告；参数稳定性检验。

---

## 12. PRE-PIT vs POST-PIT Attribution 设计

### 12.1 基线序列（归因隔离）

| 基线 | 内容 | 用途 |
|---|---|---|
| **A** | 现有代码 + 现有数据（Gate 0 冻结） | pre-PIT 对照；标记 `INVALID_FOR_VALIDATION` |
| **B1** | A + 仅市场数据 PIT 修复（Gate 3 后） | 量化**价格前视泄漏**贡献 |
| **B** | B1 + 财务数据 PIT 修复（Gate 4 后） | 量化**财报前视泄漏**贡献；= PIT-Corrected Baseline v1 |
| **C** | B + P1 修复（Gate 9 后） | 量化 ROIC bug / 字段 bug / 顺序 bug 的贡献；= Baseline v2 |

> 每步同参数、同窗口（2022-2025）、同数据 manifest，仅变更 diff 中声明的内容。

### 12.2 对照指标

| 指标 | A | B1 | B | C | A→B1 | B1→B | B→C |
|---|---|---|---|---|---|---|---|
| CAGR | | | | | | | |
| Max Drawdown | | | | | | | |
| Calmar | | | | | | | |
| 换手率 | | | | | | | |
| Coverage 漏斗 | | | | | | | |
| 持仓/行业暴露 | | | | | | | |

### 12.3 解读规则

- A→B1 显著为正 → 原收益中价格泄漏贡献大（验证 PDR 判断）；
- B1→B 一般较小（财务前视已被 2026-05 B1 修复过一轮，F-6）——预期为验证性结果；
- B→C 量化 ROIC 压 0 的系统性影响（预期拉低成长股/周期股得分分布）；
- 任何一步出现 coverage 剧变 → 先回到 Gate 5 解释，不进下一步。

---

## 13. 待用户确认项

1. ~~**回测窗口调整**（F-1 导致）：Gate 0/7 用 2022-2025 而非 2015-2024~~ → **已确认**（2026-09-01）
2. ~~**Gate 3 中间基线 B1**~~ → **已确认**（2026-09-01）
3. ~~**spike 时限**：建议 2-3 天，超时自动降级为 U0 + 偏差声明~~ → **已确认**（2026-09-01）
4. ~~**P2-2（L10 数值修订量化）**：是否纳入本计划~~ → **已确认纳入**（2026-09-01）

---

## Appendix A: Research System Evolution（2026-09-01 方向校准）

### A.1 项目定位（已确认）

> **Cyclical-Driver-System 不是自动交易机器人，而是 AI 增强型投资研究工作台**：
> 从 5000+ 上市公司中，快速、系统地发现 20-50 家值得深入研究、可能产生超额收益的标的，
> 并提供研究理由、风险与待验证项，辅助人工决策。

### A.2 PDR 阶段目标不变：数据可信底座

PIT / Coverage / Data Lineage 的必要性**一条不减**，但理由重新定义：

| 理由（错误，交易视角） | 理由（正确，研究视角） |
|---|---|
| 回测 Calmar 不可信 | **研究排序被未来函数污染 → Top50 推荐池错误 → 研究方向错误** |
| 因子 IC 被污染 → 不能选因子 | 观察池排序被污染 → 5000→50 压缩过程在给错误答案 |
| 幸存者偏差 → 回测收益虚高 | 系统发现不了“将要死掉的公司” → 漏掉最重要风险信号 |

一句话：**PIT 是投研系统的可信度底座，不是交易需要。**

### A.3 回测层重新定位：从策略验收 → 信号质量体检

回测不再回答“能不能赚钱”，而回答三个问题：

1. **排序有没有信息量？**（Top 组未来表现 vs Bottom 组，分组收益）
2. **哪些因子真正有贡献？**（IC / Rank IC 分因子归因）
3. **研究池稳定吗？**（Top50 月度留存率；若一个月全部换掉 → 信号噪声大）

核心指标调整：

| 级别 | 指标 | 回答的问题 |
|---|---|---|
| 一级 | IC / Rank IC | 分数有没有预测能力 |
| 一级 | 分组收益（Top10%/Top20%/Bottom20% 未来 1/3/6 月） | 排序单调性（最直观） |
| 二级 | 命中率（进入观察池后上涨/超额概率） | 研究池质量 |
| 二级 | 持续性（连续进入 Top50/Top100） | 信号稳定性 |
| ~~原一级~~ | ~~CAGR / Sharpe / Calmar / MaxDD~~ | 降级为参考，不验收 |

### A.4 P1 语义修复保留（用户修正）

P1（ROIC 负值压 0、roic_ttm 字段、persistence 顺序）**仍然必须修**——
不是因为交易收益，而是因为 **ROIC 等字段错误会污染 Investment Memo 解释层**（研究卡片上的“质量评分 90 / ROIC 优秀”必须是真实的）。

定位：`PIT 修复 → 研究信号验证 → 解释层修复`。不做复杂收益归因，但必须修字段。

### A.5 路线调整（四阶段）

```
Phase 1（当前）: 数据可信底座
  Gate 0-6: PIT 修复 + Coverage Audit + Data Lineage
  （不变）

Phase 2（修改）: 信号质量验证（原 Gate 7-9 改写）
  A vs B 对照 → 量化未来函数对研究排序的污染程度
  IC / Rank IC / 分组收益 / 稳定性 → 研究排序依据是否真实有效
  （不做 Calmar 最大化、不做参数优化）

Phase 3（提前）: Investment Memo Engine
  研究卡片: 公司画像 / 周期位置 / 催化剂 / 风险 / 待人工验证项
  行业比较视图: 行业内 A 收入增长最快 / B 毛利最高 / C 估值最低
  事件层: 催化日历 + 黄金坑 + 预期差（基于已有 growth_probes/sell_signals/disclosure_alert 雏形）
  输出: 每日观察池 20-50 家 + 淘汰名单 + 理由

Phase 4: 人工反馈闭环
  人工研究结果（看好/不看好/原因）→ 反哺模型校准
  （screener 标注集、Growth Source 回归测试已有雏形）
```

### A.6 对原路线的影响

| 原 Gate | 变化 |
|---|---|
| Gate 7-8（A/B1/B 回测归因） | 保留 A（污染基线，进行中）；B1/B 跑信号质量对照而非收益归因 |
| Gate 9（P1 修复） | 保留，但验收 = 解释层正确性（字段/单测），非收益 attribution |
| Gate 12（Factor Audit） | 提前到 Phase 2（信号质量验证） |
| Gate 13-14（Regime 压力测试 / Walk-forward） | 降级为参考项，不验收 |
| Gate 11（Canonical Pipeline 收敛） | 保留（研究台也需要单一真相源） |

### A.7 当前进度（2026-09-01）

- [x] Gate 0-A：性能优化（commit `b47e4c0`，三层验证全 PASS）
- [x] 方向校准：Research System Evolution（本节）
- [x] P2 Issue Log 建立（`baseline/P2_ISSUE_LOG.md`，8 项）
- [x] Gate 0-D：PRE-PIT Baseline A（commit `b7ba7a2` 归档，INVALID_FOR_VALIDATION）
- [x] Research Audit：污染样本画像（Confirmation 强 / Discovery 弱）
- [x] Gate 1：测试基建（commit `7127cc2`，characterization 9 GREEN + PIT RED）
- [x] Gate 2：PIT Contract v1（commit `d6dd7cc`，pit/ 数据可信层）
- [x] Gate 3：Market Leakage 迁移（commit `5ad171e`，PE/乖离/流动性 + P2-001）
- [x] B1 baseline（commit `b7ba7a2`，收益 132.4%→11.7%，Top100 重合 27%）
- [x] Gate 4：growth_os 财务披露治理（commit `caee7ba`，P0-2 修复）
- [x] Research System Architecture v1 + Data Asset Architecture v1（commit `caee7ba`/`1a9130d`）
- [x] TDX 财务刷新至 2026Q2 中报（commit `7beecab`，snapshot `tdx_v20260901_q2`）
- [ ] A1 baseline（价格 PIT 专用，运行中）
- [ ] B baseline（完整 PIT，运行中）
- [ ] A/A1/B1/B 四版本归因（三因素拆分）
- [ ] Phase 2：三引擎验证（H0 互补 / H1 认知差）
