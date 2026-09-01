# 数据源完整清单（2026-09-01 实勘版）

> 基于实际文件 + 代码引用，替代 DATA_INVENTORY.md 的 2026-05-30 版本

---

## 一、本地缓存（data/cache/，18 个文件）

### A. 财务数据

| # | 文件 | 大小 | 覆盖 | 来源 | 消费者 | PIT 状态 |
|---|---|---|---|---|---|---|
| 1 | `tdx_financials.csv` | **287.7MB** | 297,185 行 / 5,213 只 / **1989-12 ~ 2026-06（121 报告期）** | pytdx 解析 `~/Downloads/tdxfin/gpcw*.dat`（148 文件） | signals(S1/S2), screener(PE), valuation_filter(R035), growth_os(全部财务), wacc, probes | ✅ 披露日治理（Gate 4） |
| 2 | `financial_data.csv` | 5.2MB | 2012-03 起，ROE/OCF 比率 | akshare `stock_financial_analysis_indicator` | S5, S7, valuation_filter(neg_pe/peg) | ✅ 法定截止日过滤 |
| 3 | `quality_snapshot.csv` | 0.2MB | 2,576 只 / 20251231 期 | westock-data（商誉/有息负债/现金/权益） | valuation_filter(R008/R010) | ⚠️ 单时点快照（非 PIT） |
| 4 | `disclosure_calendar.csv` | 1.6MB | 65,693 行 / **2023Q1~2025Q4** | westock-data InfoPublDate | data_governance（披露日治理） | ✅ 治理层核心 |

### B. 行情数据

| # | 文件 | 覆盖 | 来源 | 消费者 | PIT 状态 |
|---|---|---|---|---|---|
| 5 | `~/Desktop/stocks/{code}.csv`（**5,227 只**） | **2021-01 ~ 2026-08**（F-1：无 2021 前数据） | akshare 腾讯源（含 adjustflag/isST/tradestatus 列） | signals, screener, valuation_filter, backtest, pit/market | ✅ as_of 截断（Gate 2/3） |
| 6 | `index_399300.csv`（沪深300） | 2002-01 起 | akshare | regime L0, wacc(Beta), backtest | ✅ date<=t |
| 7 | `index_399006.csv`（创业板指） | 2010-06 起 | akshare | regime L0（成长强度/回撤熔断） | ✅ |
| 8 | `index_000922_dividend.csv`（中证红利） | — | akshare | defense（DEFENSE 篮子 40%） | ✅ |
| 9 | `etf_511010_bond.csv`（国债ETF） | — | akshare | defense（防御篮子 40%） | ✅ |
| 10 | `bond_10y.csv`（10Y 国债收益率） | 2002-01 起 | akshare | regime L0 通道B, wacc(无风险利率) | ✅ |

### C. 市场状态/股票池

| # | 文件 | 覆盖 | 来源 | 消费者 |
|---|---|---|---|---|
| 11 | `stock_list.csv` | **5,515 只**，list_date 1990-12~2026-05 | akshare 多接口聚合 | universe（U0 重建） |
| 12 | `trade_calendar.csv` | 8,797 交易日，1990-12~2026-12 | akshare `tool_trade_date_hist_sina` | 全链路 |
| 13 | `margin_data.csv`（融资融券） | 2010-03 起 | akshare | regime/indicators（流动性） |
| 14 | `market_pe.csv`（上证A股PE） | — | akshare | regime/indicators（风险偏好） |

### D. 行业/战略

| # | 文件 | 内容 | 状态 |
|---|---|---|---|
| 15 | `sw_stock_industry.csv` | 5,467 只 → SW1/2/3 | ⚠️ **2026-05 单时点快照**（L2，非 PIT） |
| 16 | `sw_hierarchy.csv` + `sw_industry_map*.csv` | 申万层级与映射 | 静态 |
| 17 | `config/strategic_industries.py` | 六大战略方向（AI/电新/半导体/机器人/生命科学/商业航天） | 人工维护（Alpha 来源） |
| 18 | `pdf_financials.csv` | PDF 年报提取（客户集中度等） | 覆盖有限（~100 只级） |

### E. 原始数据（本地，非 cache）
- `~/Downloads/tdxfin/gpcw*.dat`（148 个，1988~2026Q2）→ 财务原始源
- `data/financial_reports/{code}/`（PDF 年报）→ pdf 提取源

---

## 二、外部 API（3 个供应商）

| 供应商 | 接口 | 用途 |
|---|---|---|
| **akshare** | `stock_zh_a_hist_tx` | 个股日线（腾讯源） |
| | `stock_zh_index_daily` | 指数日线 |
| | `bond_zh_us_rate` | 国债收益率 |
| | `stock_financial_analysis_indicator` | ROE/OCF |
| | `stock_info_*` / `tool_trade_date_hist_sina` | 股票列表/日历 |
| | `macro_china_margin_*` | 融资融券 |
| **pytdx** | `HistoryFinancialReader` | **财务核心源**（gpcw*.dat 解析） |
| **westock-data**（Node 子进程） | `finance {code}` | 商誉/存贷/披露日期（InfoPublDate） |
| **CNINFO**（巨潮） | 公告查询 + PDF | 年报下载 |

---

## 三、数据资产成熟度与已知限制

| 资产 | 成熟度 | 关键限制 |
|---|---|---|
| 行情 | ★★★★ | ✅ PIT；⚠️ 仅 2021+（历史窗口限 2022-2025）；复权一致性未验证（L6） |
| 财务 | ★★★★ | ✅ 披露日治理 + 2026Q2 最新；⚠️ 披露日历仅 2023-2025（更早 fallback 法定日）；L10 数值修订未量化 |
| 股票池 | ★★ | U0（当前上市重建）；缺退市 master / 历史 ST |
| 行业 | ★★☆ | 静态快照非 PIT；缺产业周期变量 |
| 战略映射 | ★★★★ | 人工 Alpha 来源 |
| 事件 | ★☆ | 有雏形（披露日/订单/客户集中度），无催化日历层 |
| 预期 | ★ | **缺失**（无一致预期/盈利预测） |
| 另类 | ★ | **缺失**（无北向/机构持仓/龙虎榜） |

---

## 四、版本与快照机制（今日新增）

| 机制 | 说明 |
|---|---|
| `data/archive/tdx_financials_{ts}.csv` | 每次回测/刷新自动归档（27 份） |
| `baseline/{a,a1,b1,b}/manifest.json` | 数据 hash + 环境 + 参数（可复现） |
| 当前财务版本 | **`tdx_v20260901_q2`**（含 2026Q2 中报） |
| 披露日历版本 | 2023Q1~2025Q4（实际披露日），更早走法定截止日 |

---

## 五、PIT 治理总表

| 资产 | 治理方式 | 状态 |
|---|---|---|
| 行情 | `pit/market.MarketData.as_of(code, t)` | ✅ 完成 |
| 财务 | `data_governance.filter_available_reports`（实际披露日→法定日） | ✅ 完成 |
| 股票池 | `pit/universe.UniverseData`（U0 + limitation 声明） | ⚠️ U0 |
| 行业 | `pit/industry.IndustryData`（静态 + limitation） | ⚠️ 静态 |
| 事件/预期/另类 | 未接入 | 路线图 P0/P1 |
