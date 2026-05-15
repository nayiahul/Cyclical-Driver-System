# Slice 1: 交易日历 + 股票池 + 等权回测 设计文档

**日期**: 2026-05-14
**关联**: V4.2 周期驱动三因子动态选股系统
**策略**: 端到端薄切片 — 最小链路跑通后再逐层加复杂度

---

## 1. 目标

用最小实现验证"数据获取 → 股票池 → 调仓 → 净值"链路完整可运行。等权组合，无因子评分，无优化器。

## 2. 架构

```
main.py                    # 入口：跑回测，输出净值 CSV 和简单统计
├── calendar.py            # 交易日历
├── universe.py            # 股票池获取与过滤
└── backtest/
    └── engine.py          # 等权回测引擎
```

模块间通过函数调用通信，所有接口接受/返回 `pd.DataFrame` 或基本类型。

## 3. 模块详设

### 3.1 calendar.py

**职责**：提供 A 股交易日历与调仓日期。

**函数**：

| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `get_trade_calendar(start, end)` | str, str | `pd.DataFrame` (date, is_trade_day) | 从 AKShare 获取全量交易日 |
| `get_rebalance_dates(start, end)` | str, str | `list[str]` | 每月首个交易日列表 |
| `get_t_date(rebalance_date)` | str | `str` | 调仓日前一个交易日（即月末确认日） |

**数据源**：`akshare.tool_trade_date_hist_sina()`

**实现要点**：
- 调仓逻辑为月末确认、月初执行：`rebalance_date` = 每月首个交易日，`t_date` = 该日前最近交易日
- 缓存到本地 CSV 避免重复请求

### 3.2 universe.py

**职责**：按调仓日获取可交易股票池。

**函数**：

| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `get_stock_list()` | — | `pd.DataFrame` | 全部 A 股基础信息（代码、名称、上市日、退市日、申万行业） |
| `get_universe(trade_date)` | str | `list[str]` | 该日可交易股票代码列表 |

**过滤规则**（薄切片阶段）：
- 已上市 (ipo_date <= trade_date)
- 未退市 (delist_date is None or delist_date > trade_date)
- 非 ST（股票名称不含 ST/ \*ST）
- 非上市首月新股（ipo_date < trade_date - 20 trading days）

**数据源**：
- 股票列表：`akshare.stock_info_a_code_name()`
- 行业分类：`akshare.stock_board_industry_name_em()` 逐股映射
- ST 判断：名称字符串匹配（回测阶段，后续会升级到 ST 事件日历）

**淘汰池记录**：`universe.py` 输出每期被过滤掉的股票及原因，写入日志。

### 3.3 backtest/engine.py

**职责**：遍历调仓日，等权分配，模拟成交，记录净值。

**核心函数**：

| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `run_backtest(start, end, initial_capital)` | str, str, float | `BacktestResult` | 主循环 |
| `get_open_prices(codes, rebalance_date)` | list, str | `pd.Series` | 获取开盘价（回测中的成交价） |
| `compute_returns(positions, prices_prev, prices_now)` | dict, series, series | `float` | 计算组合区间收益 |

**调仓流程**（每个 rebalance_date）：

```
1. t_date = get_t_date(rebalance_date)         # 月末确认日
2. universe = get_universe(t_date)              # 月末时点的可交易股票
3. weights = {code: 1/len(universe) for code in universe}  # 等权
4. open_prices = get_open_prices(universe, rebalance_date)  # 月初开盘价成交
5. 换仓：卖出不在新 universe 的持仓，买入新标的
6. 记录持仓、现金、净值
```

**成本与约束**：
- 双边交易成本 0.3%（佣金+印花税+滑点）
- 单票权重上限 8%：若 universe < 13 只，多余资金留作现金
- 最小持仓数 15 只：若 universe < 15 只，发行日志警告，不做额外处理

**输出**：

`BacktestResult` dataclass 包含：
- `nav_series: pd.Series` — 每日净值序列
- `daily_returns: pd.Series` — 日收益率
- `trades: pd.DataFrame` — 每笔交易记录（日期、代码、方向、数量、价格）
- `stats: dict` — 统计（年化收益、年化波动、夏普比率、最大回撤、Calmar 比率、胜率）

### 3.4 main.py

```
from calendar import get_rebalance_dates
from universe import get_universe
from backtest.engine import run_backtest

if __name__ == "__main__":
    result = run_backtest("2015-01-01", "2024-12-31", initial_capital=1e8)
    stats = result.stats
    print(stats)
    result.nav_series.to_csv("output/nav.csv")
    result.trades.to_csv("output/trades.csv")
```

## 4. 数据流

```
AKShare API
    │
    ▼
calendar.py ──→ rebalance_dates (每月一个)
    │
    ▼
universe.py ──→ stock_list per t_date
    │
    ▼
backtest/engine.py ──→ 等权持仓 → 净值曲线
    │
    ▼
output/nav.csv + trades.csv
```

## 5. 项目目录（首层）

```
周期驱动因子系统/
├── main.py
├── calendar.py
├── universe.py
├── backtest/
│   ├── __init__.py
│   └── engine.py
├── output/
│   ├── nav.csv
│   └── trades.csv
├── data/                    # 缓存日历、股票列表
│   └── cache/
├── config/
│   └── params.py            # 常量（成本率、权重上限等）
├── docs/
│   ├── README.md
│   └── superpowers/
│       └── specs/
│           └── 2026-05-14-slice1-*.md
└── .venv/
```

## 6. 成功标准

- [ ] 获取 2015-01-01 到 2024-12-31 的交易日历，输出调仓日期列表无间断
- [ ] 任取 3 个调仓日，universe 返回数量 > 2000 只、无 ST、无未上市新股
- [ ] 回测跑完 10 年无异常，输出净值 CSV 和基础统计
- [ ] 年化换手率合理（< 500%）
- [ ] 夏普比率和最大回撤在合理范围内（与沪深300等权基准比较）

## 7. 已知局限（留给后续切片）

- ST 判断依赖名称字符串，不如事件日历精确
- 行业映射用 AKShare 自带分类，未统一到申万 2024
- 未处理停牌、涨跌停不可交易情况
- 现金不计息
- 无因子评分、无优化、无风控
