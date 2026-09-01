# PIT Contract v1 — 数据可信层设计文档

**状态**: 已实现（Gate 2，commit 待定）
**目标**: 任何研究模块只能看到截至研究时点真实可获得的信息

---

## 一、语义定义

```
as_of(t) = 截至 t 日收盘已公开、已可得的数据（闭区间，含 t 日）

observation_time: 信号计算时点（当前 = 调仓日前一交易日收盘）
execution_time:   交易执行时点（当前 = 调仓日收盘）
```

## 二、包结构（pit/）

```
pit/
├── __init__.py      # 统一导出
├── contracts.py     # DataPoint (D9 lineage) + as_of 语义文档
├── exceptions.py    # PITViolation / FutureDataError / MissingDataError
├── market.py        # MarketData: as_of / close_on_or_before / effective_date / has_future_data / coverage
├── financial.py     # FinancialData: snapshot / quarterly_series / disclosure_info
├── universe.py      # UniverseData: as_of (U0) / membership / limitation
├── industry.py      # IndustryData: as_of (静态快照) / limitation
└── guard.py         # PITGuard: requested vs actual 审计 + HARD ERROR
```

## 三、硬不变量

| 数据 | 不变量 | 违反行为 |
|---|---|---|
| 行情 | max(price.date) <= t（as_of 截断视图） | as_of 截断（核心语义）；guard 层 HARD ERROR |
| 财务 | max(disclosure_cutoff) <= t | filter_available_reports 过滤 |
| Universe | list_date <= t 且 (delist_date is None or > t) | U0 未实现 delist（已声明限制） |
| 行业 | 静态快照（2026-05） | 显式 limitation 声明 |

## 四、缺失语义（D5）

| 场景 | 行为 |
|---|---|
| 数据源含未来行（本地文件更新到 2026） | as_of 截断返回 ≤t 视图（正常回测场景） |
| 请求 t 早于数据源开始 | 返回空 DataFrame（UNAVAILABLE） |
| 完全无数据（新股/停牌） | 返回空 / None |
| guard 检测到 actual > requested | **PITViolation (HARD ERROR)** |
| fallback 到未来/当前数据补历史 | FORBIDDEN（guard 拦截） |
| prior-known fallback（close_on_or_before） | 允许（执行价查询白名单语义） |

## 五、关键设计决策

1. **as_of 永不 raise**：本地价格文件天然含未来行（下载到 2026），回测请求 2022 必须截断而非崩溃。HARD ERROR 属于 PITGuard 审计层。
2. **loader 动态解析**：MarketData 不缓存 loader 绑定，支持测试 monkeypatch `pit.market._raw_loader`。
3. **复用既有治理层**：FinancialData 内部调用 `data_governance.filter_available_reports`（实际披露日历 → 法定截止日），不复制逻辑。
4. **零行为变更**：screener 的 compute_rps60 / compute_industry_momentum / compute_theme_rps 价格读取改为 `_MARKET.as_of(code, t_date)`，计算逻辑不变，只是输入被截断。

## 六、违反规则清单（Gate 2 阶段）

| 文件 | 违反点 | 状态 |
|---|---|---|
| screener.py | RPS60/行业动量/theme RPS `iloc[-1]` 全量读取 | ✅ 已迁移（Gate 2） |
| screener.py | PE 计算 L274/L319 价格 | ⏳ Gate 3 |
| valuation_filter.py | 乖离率 L93-94/流动性 L158 | ⏳ Gate 3（且数据源指向空目录 P2-001） |
| signals.py | S3/S4（compute_alpha 路径） | ⏳ Gate 3 |
| growth_os/data.py | 财务绕过披露治理（P0-2） | ⏳ Gate 4 |

## 七、测试状态（Gate 2 Exit）

```
tests/pit/test_providers.py     13 passed（Provider 级: as_of 截断/guard/lineage/披露）
tests/pit/test_pit_contract.py  T-MKT-01/02 GREEN（迁移后）+ T-FIN GREEN + U xfail
tests/characterization/          9 passed（语义锁未破坏）
```

## 八、审计说明（未来数据防火墙）

PITGuard 上下文管理器记录 `(module, code, requested_as_of, actual_date)`：
- 回测运行时 wrap 数据访问，任意 actual > requested → PITViolation
- 与 engine audit_dir（每调仓日 hash）配合，构成双层防火墙
