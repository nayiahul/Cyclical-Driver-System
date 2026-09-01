# Gate 0-A — 性能优化方案（无语义变更）

**状态**: 已批准执行（边界：允许缓存/向量化/去重读；禁止改因子公式/权重/排序/缺失处理/交易逻辑）
**依据**: cProfile 单日剖析（compute_composite 204 秒/调仓日；全窗口 5-7 小时/次）
**验收**: 三层语义一致（Level 1 排名 / Level 2 交易 / Level 3 NAV 浮点级）

---

## 一、耗时分布（cProfile，单调仓日 compute_composite）

| 热点 | 耗时 | 占比 | 性质 |
|---|---|---|---|
| `data_governance._compute_cutoff_map` iterrows 87万行 + object 字符串比较 | ~68s（filter×3）+80s（比较） | ~45% | 工程实现：逐行循环 + 字符串逐格比较 |
| `read_csv` tdx_financials.csv（283MB）× 3-4 次/调仓日 | ~15-20s × 4 | ~15% | IO 重复读取 |
| `fin[fin["code"]==code]` 全表过滤 × 4000+ 股票 | ~80s | ~30% | 工程实现：O(N) 字符串比较 × N 次 |
| `compute_rps60` 首次全量价格加载 | ~36s（仅首个调仓日） | — | 一次性成本，已有 mem cache |
| 其余（S5/S7/PE 计算） | ~30s | ~10% | 算法本体，不动 |

结论：~90% 耗时是工程重复计算，非算法本身。优化不改任何数值。

---

## 二、修改清单（文件 / 函数 / 改前 / 改后 / 验证）

### OPT-1 `data_governance.py::_compute_cutoff_map`（收益最大）

| 项 | 内容 |
|---|---|
| 修改前 | `for _, row in df.iterrows()` 逐行构造 `(code, report_date)` key 查 calendar dict；statutory 逐行调 `get_disclosure_cutoff` |
| 修改后 | ① statutory 向量化：`report_date_str` 按后 4 位 `np.select` 映射法定截止日（0331→0430 / 0630→0831 / 0930→1031 / 1231→次年0430）；② calendar lookup 向量化：预构建 `{code+report_date: disclosure}` flat dict，`pd.Series(keys).map(flat)`，NaN 处填 statutory |
| 语义等价性 | 同一 (code, report_date) → 同一 disclosure；YYYYMMDD 字符串拼接无歧义（6 位 code + 8 位 date）；np.select 分支与原 if/elif 完全同构 |
| 验证 | 构造 100 行含四类报告期 + 日历命中/未命中的 df，新旧函数输出逐位一致（测试 T-PERF-01） |

### OPT-2 共享 TDX 加载（去重复读盘）

| 项 | 内容 |
|---|---|
| 修改前 | `signals.py` S1/S2、`screener.py` compute_composite/screen、`valuation_filter.py` 各自 `pd.read_csv("data/cache/tdx_financials.csv")`，每调仓日 4 次读 283MB |
| 修改后 | `data_governance.py` 新增 `load_tdx_raw()`（模块级缓存，文件不存在返回 None）；5 处替换；调用处对 None 的降级逻辑与原 `if os.path.exists` 分支逐一对齐 |
| 语义等价性 | 同一路径、同一 dtype 解析（`code:str, report_date_str:str`），内容逐位一致；None 降级语义与 os.path.exists 守卫等价 |
| 验证 | 两处调用返回 `df.equals(原 read_csv 结果)`；T-PERF-02 |

### OPT-3 按 code 的 groupby 预分组（消除 80s 全表过滤）

| 项 | 内容 |
|---|---|
| 修改前 | S1 两处循环、S2 循环、compute_composite/screen 的 ttm_eps 循环：每股票 `fin[fin["code"]==code].sort_values("report_date_str")`，87万行 × 4000+ 次 O(N) object 比较 |
| 修改后 | 循环前一次 `by_code = {c: g.sort_values("report_date_str") for c, g in fin.groupby("code")}`；循环内 `by_code.get(code, _EMPTY)` |
| 语义等价性 | groupby 保持组内文件顺序 → sort_values 后与原过滤+排序结果逐位一致；`_EMPTY` 空 DataFrame 与 `len<4 continue` 分支等价 |
| 验证 | 同一 t_date 下新旧循环输出分数 Series 逐位一致；T-PERF-03 |

### OPT-4 `universe.py::get_universe` + `trade_calendar.py::get_trade_calendar` 缓存

| 项 | 内容 |
|---|---|
| 修改前 | 每调仓日重新 read_csv stock_list.csv + trade_calendar.csv 并重建（~2 分钟/次 × 48） |
| 修改后 | `get_universe` 按 t_date 缓存（返回 `.copy()` 防调用方 mutate）；`get_trade_calendar` 缓存全表后切片 |
| 语义等价性 | 纯函数同输入同输出；copy 不改变内容 |
| 验证 | 缓存前后两次调用 `df.equals`；T-PERF-04 |

### 明确不改（边界冻结）

- `valuation_filter.py::_load_price_data` 指向 `data/cache/daily_prices/`（**当前为空目录 → 乖离率/流动性规则恒不触发**）——这是 PDR 之外发现的**数据源指向问题**（应指向 STOCKS_DIR），但**修改它会改变缺失处理行为**，违反本轮边界。记录为 Gate 3 修复项（迁移 MarketData.as_of 时统一数据源并验证规则恢复）。
- 因子公式 / 权重 / 排序 / 交易执行 / engine 时序：一律不动。
- `compute_S3/S4`（compute_alpha 路径，不在主回测）：不动。

---

## 三、验证方案（三层）

| 层级 | 方法 | 通过标准 |
|---|---|---|
| Level 1 决策一致 | 固定调仓日 2023-06-30（t_date=20230630）：优化前 vs 优化后 输出 candidate list / 全量 scores / rank / Top100 / regime | 完全一致（逐位） |
| Level 2 交易一致 | 小窗口 2022-01~2022-06 回测：trades（buy/sell/日期/仓位）对比 | 完全一致 |
| Level 3 NAV | 同上窗口 nav_series 对比 | `abs(diff) < 1e-8`（期望 0） |

对照样本已先行存档：`/tmp/bench_old/one_day_20230630.json`、`/tmp/bench_old/window_nav_old.csv`、`/tmp/bench_old/window_trades_old.csv`。

## 四、预期收益

| 阶段 | 耗时 |
|---|---|
| 优化前（实测） | ~7 分钟/调仓日；~5.5-7 小时/48 月窗口 |
| 优化后（实测） | ~1.4 分钟/调仓日；48 月窗口预估 1-1.5 小时 |

## 五、验收结果（2026-09-01 完成）

| 层级 | 结果 | 证据 |
|---|---|---|
| 单元等价 T-PERF-01/02/03 | PASS | cutoff map 向量化 / load_tdx_raw / groupby 逐位一致 |
| valuation 三表 groupby | PASS | tdx/quality/fin 800 只逐位一致（含空表 dtype 保留修正） |
| Level 1 决策一致 | PASS | 2023-06-30：3099 只分数 0 差异、Top100 一致、regime=BEAR 一致 |
| Level 2 交易一致 | PASS | 2022H1：730 笔交易日期/代码/方向/数量/价格/成本逐字段一致 |
| Level 3 NAV 一致 | PASS | NAV 最大绝对差 0.0（<1e-8） |
| 审计钩子零影响 | PASS | audit on/off：NAV 差 0.0、trades 730=730 |

**提交**: `b47e4c0`（独立 commit，与 PIT 修复隔离）

**审计输出**: 新增 `audit_dir` 参数（默认 None 零开销），每调仓日输出 universe/score/ranking/portfolio/trade hash + 每日 nav hash，供未来审计追溯。

**遗留（不阻塞）**: `valuation_filter._load_price_data` 仍指向空目录 `data/cache/daily_prices/`（乖离率/流动性规则当前不触发）——Gate 3 迁移 MarketData.as_of 时统一数据源并验证规则恢复。

优化完成后：单日验证 → 小窗口验证 → 通过后跑正式 PRE-PIT Baseline（Gate 0-D）。
