# 数据清单

Growth OS 全部数据源、来源、消费者及刷新策略。

---

## 一、本地缓存文件（19个）

### 1. `data/cache/tdx_financials.csv`
- **内容**: 全A股季度财务数据（营收/扣非净利润/毛利率/合同负债/CAPEX/ROIC/经营现金流/有息负债等100+字段）
- **来源**: pytdx `HistoryFinancialReader` 解析本地 `~/Downloads/tdxfin/gpcw*.dat`
- **构建**: `tdx_financials.py`
- **消费者**: `data.py`(核心加载), `signals.py`, `screener.py`, `valuation_filter.py`, `wacc.py`, `growth_probes.py`, `report.py`, `diagnostics/valuation.py`
- **刷新**: 手动运行 `tdx_financials.py`

### 2. `data/cache/daily_prices/{code}.csv`
- **内容**: 个股日线行情（日期/收盘价/成交量等），~4891只
- **来源**: akshare `stock_zh_a_hist_tx`（腾讯源）
- **消费者**: `data.py`(get_price_data), `signals.py`, `risk_factors.py`, `valuation_filter.py`, `screener.py`
- **刷新**: 按需，三级回退：`~/Desktop/stocks/` → `data/cache/daily_prices/` → akshare实时

### 3. `data/cache/index_399300.csv`
- **内容**: 沪深300日线
- **来源**: akshare `stock_zh_index_daily(symbol="sz399300")`
- **消费者**: `regime.py`(L0通道A), `wacc.py`(Beta基准), `regime/indicators.py`, `backtest.py`, `industry_indicators.py`, `risk_factors.py`
- **刷新**: 按需缓存

### 4. `data/cache/index_399006.csv`
- **内容**: 创业板指日线
- **来源**: akshare `stock_zh_index_daily(symbol="sz399006")`
- **消费者**: `regime.py`(L0通道A+C: 成长相对强度+回撤熔断)
- **刷新**: 按需缓存

### 5. `data/cache/bond_10y.csv`
- **内容**: 中国10年期国债收益率日频
- **来源**: akshare `bond_zh_us_rate()`
- **消费者**: `regime.py`(L0通道B: 利率压力), `data.py`(无风险利率)
- **刷新**: 按需缓存

### 6. `data/cache/index_000922_dividend.csv`
- **内容**: 中证红利指数(000922)日线
- **来源**: akshare `stock_zh_index_daily(symbol="sh000922")`
- **消费者**: `defense.py`(DEFENSE防御篮子40%)
- **刷新**: 按需缓存

### 7. `data/cache/etf_511010_bond.csv`
- **内容**: 国债ETF(511010)日线
- **来源**: akshare `fund_etf_hist_em(symbol="511010")`
- **消费者**: `defense.py`(DEFENSE防御篮子40%)
- **刷新**: 按需缓存

### 8. `data/cache/trade_calendar.csv`
- **内容**: A股交易日历
- **来源**: akshare `tool_trade_date_hist_sina()`
- **消费者**: `trade_calendar.py`, `universe.py`, `signals.py`, `screener.py`, `regime/detector.py`
- **刷新**: 按需（日期超出缓存范围时）

### 9. `data/cache/stock_list.csv`
- **内容**: 全A股代码+名称+上市日期
- **来源**: akshare多接口聚合: `stock_info_a_code_name()`, `stock_info_sz_name_code()`, `stock_info_sh_name_code()`, `stock_info_bj_name_code()`, `stock_individual_info_em()`
- **消费者**: `universe.py`, `signals.py`, `build_quality_cache.py`, `build_disclosure_calendar.py`
- **刷新**: 缓存损坏/缺失时重建

### 10. `data/cache/financial_data.csv`
- **内容**: 加权ROE + 经营现金流/营收比率
- **来源**: akshare `stock_financial_analysis_indicator()`
- **消费者**: `signals.py`(S5盈利稳定性, S7现金流质量), `valuation_filter.py`
- **刷新**: 一次性构建，静态缓存

### 11. `data/cache/disclosure_calendar.csv`
- **内容**: 实际财报披露日期（报告期→公告日映射）
- **来源**: westock-data Node.js 脚本
- **消费者**: `data_governance.py`(前视偏差消除)
- **刷新**: `build_disclosure_calendar.py`，支持`--full`全量

### 12. `data/cache/quality_snapshot.csv`
- **内容**: 资产负债表质量字段（商誉/有息负债/现金等价物/权益/存货/应收）
- **来源**: westock-data Node.js 脚本
- **消费者**: `valuation_filter.py`(R008商誉/净资产, R010存贷双高)
- **刷新**: `build_quality_cache.py`

### 13. `data/cache/pdf_financials.csv`
- **内容**: PDF提取的结构化数据（存货构成/研发资本化率/政府补助/账龄/客户集中度/分部收入）
- **来源**: `pdf_data.py` 从 `data/financial_reports/{code}/` 下PDF年报提取
- **消费者**: `growth_probes.py`(探针4: 客户集中度), `funnel.py`(PDF增强信号)
- **刷新**: 按需 `build_pdf_cache()`

### 14. `data/cache/market_pe.csv`
- **内容**: 上证A股市盈率历史
- **来源**: akshare `stock_market_pe_lg(symbol="上证A股")`
- **消费者**: `regime/indicators.py`(风险偏好代理)
- **刷新**: 按需缓存

### 15. `data/cache/margin_data.csv`
- **内容**: 沪深两市融资融券余额
- **来源**: akshare `macro_china_market_margin_sh()` + `macro_china_market_margin_sz()`
- **消费者**: `regime/indicators.py`(流动性指标)
- **刷新**: 按需缓存

### 16. `docs/sw_index_third_cons.csv`
- **内容**: 申万三级行业分类映射（股票代码→三级行业）
- **来源**: 手动维护
- **消费者**: `data.py`(load_industry_map), `run_screen.py`
- **刷新**: 随申万分类更新

### 17. `data/cache/sw_stock_industry.csv`
- **内容**: 股票代码→L1/L2/L3申万行业
- **来源**: `industry.py` 生成
- **消费者**: `industry.py`, `signals.py`, `screener.py`
- **刷新**: 静态

### 18. `data/cache/sw_hierarchy.csv`
- **内容**: 申万行业层级信息
- **来源**: 同行业映射
- **消费者**: `industry.py`
- **刷新**: 静态

### 19. `config/tdx_fields.csv`
- **内容**: TDX gpcw字段定义（列索引/名称/类别/单位/有效范围）
- **来源**: 通达信官方Excel手工转换
- **消费者**: `config/tdx_fieldmap.py`, `tdx_financials.py`
- **刷新**: 通达信格式变更时

---

## 二、外部API（3个供应商）

### AKShare（开源金融数据库）

| 接口 | 调用位置 | 获取内容 |
|------|---------|---------|
| `stock_zh_a_hist_tx` | `data.py` | 个股日线行情（腾讯源） |
| `stock_zh_index_daily` | `data.py`, `regime.py`, `industry_indicators.py`, `defense.py` | 指数日线（沪深300/创业板指/中证红利） |
| `bond_zh_us_rate` | `data.py`, `regime.py` | 国债收益率曲线 |
| `stock_market_pe_lg` | `data.py`, `regime/indicators.py` | 市场PE（沪深300/上证A股） |
| `stock_financial_analysis_indicator` | `signals.py` | 加权ROE+OCF/营收 |
| `stock_info_*` | `universe.py` | 股票代码/名称/上市日期 |
| `tool_trade_date_hist_sina` | `trade_calendar.py` | 交易日历 |
| `macro_china_market_margin_*` | `regime/indicators.py` | 融资融券余额 |
| `macro_china_pmi_yearly` | `industry_indicators.py` | 制造业PMI |
| `macro_china_industrial_production_yoy` | `industry_indicators.py` | 工业增加值 |
| `macro_china_exports_yoy` | `industry_indicators.py` | 出口增速 |
| `macro_china_society_electricity` | `industry_indicators.py` | 用电量 |
| `stock_board_industry_hist_em` | `industry_indicators.py` | 行业板块月线动量 |
| `fund_etf_hist_em` | `defense.py` | 国债ETF行情 |

### CNINFO（巨潮资讯网）

| 端点 | 用途 |
|------|------|
| `GET cninfo.com.cn/new/data/szse_stock.json` | orgId解析 |
| `POST cninfo.com.cn/new/hisAnnouncement/query` | 年报/半年报列表查询 |
| `adjunctUrl` 字段构建的PDF URL | PDF年报下载 |

### westock-data（Node.js 子进程）

| 命令 | 输出 |
|------|------|
| `node index.js finance {code} --num N` | 资产负债表质量字段（商誉/有息负债/现金/权益/存货/应收） |
| 披露日期查询 | 实际财报公告日（InfoPublDate） |

---

## 三、派生/计算指标

| 模块 | 指标 | 依赖原始数据 |
|------|------|------------|
| `data.py` | TTM ROIC（8季去累计化NOPAT/平均投入资本） | #1 |
| `data.py` | 营收3年CAGR | #1 |
| `data.py` | 同比增速（滚动4季/去年同期） | #1 |
| `data.py` | 市值（收盘价×总股本） | #1 + #2 |
| `wacc.py` | Beta（504日OLS vs 沪深300） | #2 + #3 |
| `wacc.py` | ERP（Damodaran 5.5% + 盈利收益率法） | #3 + #5 + #14 |
| `wacc.py` | 债务成本（利息/有息债务） | #1 |
| `wacc.py` | WACC（CAPM + 债务加权，底部保护max(r_f+3%,4.7%)） | 上述全部 |
| `funnel.py` | L2护城河分（GM趋势/费用杠杆/合同负债增长/研发强度） | #1 |
| `funnel.py` | L3 ROIC-WACC利差Sigmoid | wacc派生 + #1 |
| `funnel.py` | L5 PEG（PE/g_proxy，g_proxy=EWA营收增速×合同负债交叉验证×OCF折价） | #1 + #2 |
| `growth_probes.py` | 订单领先性（合同负债vs营收） | #1 |
| `growth_probes.py` | CAPEX效率（CAPEX流出vs ROIC） | #1 |
| `growth_probes.py` | 毛利率韧性（12季趋势+波动率） | #1 |
| `growth_probes.py` | 客户集中度（前5/前1占比） | #13 |
| `lifecycle.py` | 生命周期（导入期/加速期/成熟期/衰退期） | #1 |
| `signals.py` | S1利润加速度（扣非同比趋势） | #1 |
| `signals.py` | S2产能扩张（合同负债+CAPEX+固定资产+ROE趋势） | #1 |
| `signals.py` | S3个股动量（RPS60行业内百分位） | #2 |
| `signals.py` | S4行业共振（行业内收益集中度） | #2 |
| `signals.py` | S5盈利稳定性（ROE波动） | #10 |
| `signals.py` | S7现金流质量（OCF/营收） | #10 |
| `regime/indicators.py` | 指数趋势（均线交叉） | #3 |
| `regime/indicators.py` | 市场广度（60日MA20超越比） | #3 |
| `regime/indicators.py` | 风险偏好（上证PE 60日变化） | #14 |
| `regime/indicators.py` | 流动性（融资余额变化） | #15 |
| `industry_indicators.py` | 行业动量（vs沪深300） | akshare行业板块 |
| `industry_indicators.py` | 产业周期热度（PMI/IP/出口/用电） | akshare宏观 |
| `defense.py` | 防御组合收益（40%红利+40%国债+20%现金） | #6 + #7 |

---

## 四、数据流向

```
通达信 gpcw*.dat ──pytdx──→ tdx_financials.csv ─────┐
akshare 日线 ────────────→ daily_prices/*.csv ──────┤
akshare 指数/利率 ───────→ #3 #4 #5 #6 #7          ├──→ data.py ──→ funnel.py ──→ scorecard.py
akshare 财务指标 ────────→ financial_data.csv ──────┤                              │
akshare 宏观/行业板块 ───→ industry_indicators ─────┤                              ▼
CNINFO API ─────────────→ PDF年报 ──→ pdf_fin.csv ──┤                        result_df
westock-data ───────────→ quality_snapshot.csv ────┘                              │
                                                                                  ▼
                                                                          Growth Source
                                                                          classifier.py
```

---

## 五、未使用的常见数据源

tushare, baostock, wind, joinquant — 均未接入。

---

*最后更新: 2026-05-30*
