# 周期驱动因子系统 — 全面分析报告 (PDR 预备材料)

**日期**: 2026-08-05 | **版本**: v3.0 系 | **作者**: 系统自动分析

---

## 一、工具链 (Toolchain)

### 1.1 语言与运行时

| 组件 | 版本/说明 |
|------|----------|
| Python | 3.x（虚拟环境 `.venv/`） |
| pip 依赖 | pandas 2.2.2, numpy 1.26.4, scipy 1.17.1, akshare 1.18.63, loguru, matplotlib, pytdx |

### 1.2 数据源（5 级数据栈）

```
第一级: 通达信本地文件 (pytdx)
  └─ ~/Downloads/tdxfin/gpcw*.dat → tdx_financials.py 解析
  └─ 输出: data/cache/tdx_financials.csv (100+ 字段/季度)

第二级: AKShare 在线 API
  └─ 个股日线 (stock_zh_a_hist_tx, 腾讯源)
  └─ 指数日线 (stock_zh_index_daily): 沪深300/创业板指/中证红利
  └─ 宏观数据: PMI/国债收益率/融资余额
  └─ 基金: 国债ETF 511010

第三级: Sina 财经
  └─ 交易日历 (tool_trade_date_hist_sina)
  └─ 申万行业分类 (sw_classify.py)

第四级: westock-data 披露日历
  └─ InfoPublDate 实际公告日期
  └─ 输出: data/cache/disclosure_calendar.csv

第五级: PDF 财报原文
  └─ growth_os/pdf_download.py → pdf_extract.py → pdf_data.py
  └─ 结构化提取: 营收/利润/现金流/合同负债
```

### 1.3 本地缓存文件（19 个）

| 缓存文件 | 内容 | 刷新方式 |
|---------|------|---------|
| `tdx_financials.csv` | 全A股季度财务(100+字段) | 手动 `python tdx_financials.py` |
| `daily_prices/{code}.csv` | 个股日线(~4891只) | 按需，三级回退 |
| `index_399300.csv` | 沪深300日线 | 按需缓存 |
| `index_399006.csv` | 创业板指日线 | 按需缓存 |
| `bond_10y.csv` | 10Y国债收益率 | 按需缓存 |
| `index_000922_dividend.csv` | 中证红利指数 | 按需缓存 |
| `etf_511010_bond.csv` | 国债ETF | 按需缓存 |
| `trade_calendar.csv` | A股交易日历 | 按需缓存 |
| `stock_list.csv` | 全A股代码+名称+上市日期 | 按需缓存 |
| `sw_stock_industry.csv` | 申万三级行业映射 | 手动生成 |
| `sw_hierarchy.csv` | 申万行业层级结构 | 手动生成 |
| `disclosure_calendar.csv` | 实际公告日期(5508只) | `python build_disclosure_calendar.py` |
| `financial_data.csv` | 合并财务数据 | 按需 |
| `pdf_financials.csv` | PDF提取的财务数据 | 按需 |
| `quality_cache.csv` | 质量因子缓存 | `python build_quality_cache.py` |

### 1.4 工具脚本

| 脚本 | 功能 |
|------|------|
| `tdx_financials.py` | 通达信财务数据刷新 |
| `build_disclosure_calendar.py` | 披露日历构建 |
| `build_quality_cache.py` | 质量因子缓存重建 |
| `sweep.py` | 参数网格扫描(TOP_N × PEG_MAX) |
| `tools/gen_label_todo.py` | 标注任务生成 |
| `tools/run_regression_test.py` | 回归测试 |

### 1.5 诊断工具

| 工具 | 功能 |
|------|------|
| `diagnostics/attribution.py` | Brinson 绩效归因 |
| `diagnostics/drawdown.py` | 回撤归因分析 |
| `diagnostics/factor_corr.py` | 因子相关性矩阵 |
| `diagnostics/themes.py` | 主题动量分析 |
| `diagnostics/valuation.py` | 估值诊断 |
| `diagnostics/volatility.py` | 波动率诊断 |
| `diagnostics/quality_coef.py` | 质量系数校准 |
| `diagnostics/probe_accuracy_study.py` | 探针准确率研究 |
| `diagnostics/check_2022_picks.py` | 2022年选股回顾 |

---

## 二、项目背景 (Background)

### 2.1 核心问题

A股市场存在结构性挑战：
- **5000+ 只股票**，人工覆盖不可能
- **财务数据噪声大**，单一指标误导性强
- **市场风格切换频繁**，静态因子失效快
- **制度特殊性**：季报披露滞后、涨跌停、T+1

### 2.2 策略定位

**主动基本面景气策略（非统计套利 Alpha）**

| 维度 | 定位 |
|------|------|
| 策略类型 | 基本面多因子选股 |
| 投资周期 | 月度调仓，中长期持有 |
| 目标函数 | 最大化 Calmar Ratio（约束：回撤 ≤ 35%） |
| 风格偏倚 | 成长股优先，允许行业偏离 |
| 可解释性 | 每一层决策可追溯、可审计 |
| 基准 | 沪深300 |

### 2.3 演进历程

```
v1.0 (基线) → 单因子 Z-Score + 简单排雷
v2.0 → 六层漏斗 + 三态 Regime + 风控体系
v2.3-2.5 (Sprint 17-19) → 分类器稳定 + 生命周期防抖 + 行业守卫
v3.0 (当前) → Regime路由引擎 + 范式×生命周期2D权重 + CAPEX周期定位
v4.0 (规划中) → L2费用率闸 + L3 Sigmoid架构级校准
```

### 2.4 关键设计约束

- 无测试套件，通过 diagnostics/ 下诊断脚本验证
- 所有计算使用 T 月末已确认数据，调仓在 T+1 月首个交易日
- 财务数据严禁前视偏差（`data_governance.py` 披露截止日治理）

---

## 三、设计思路 (Design Philosophy)

### 3.1 核心哲学：三层表达分离

```
Space A (Eligibility):  L1 排雷 pass_l1 → 硬闸门
Space B (Quality):      L2+L3+L4 → Regime特定评分
Space C (Expectation):  L5 → Regime特定估值框架

Top20 = argmax(B + C | A == pass)
```

**原则**: 合格性判断（能不能投）与质量评分（好不好）与估值判断（贵不贵）完全解耦。

### 3.2 漏斗哲学：逐层淘汰，不累积惩罚

每一层只做一件事，不把上层的疑虑带下来变成下层的扣分。

### 3.3 周期驱动哲学：一切权重都是周期的函数

- 市场周期(Regime) 决定仓位上限和因子权重倾斜
- 个股生命周期(Lifecycle) 决定五层漏斗的权重分配
- 行业范式(Paradigm) 决定用哪些探针、用什么估值框架
- CAPEX周期 决定产能扩张是加分还是减分

### 3.4 可解释性优先于预测精度

每只股票最终决策可追溯到：
- 触发了哪些 L1 红灯
- L2-L5 各层得分来源
- Regime 路由路径
- 生命周期阶段 + 判定依据

### 3.5 防御性设计

| 机制 | 触发条件 |
|------|---------|
| Regime DEFENSE | 三通道触发 → 切防御资产(中证红利40%+国债ETF40%+现金20%) |
| L1 条件红灯收紧 | CAUTION/DEFENSE 模式下 1 项即淘汰 |
| 连续仓位上限 | BEAR=60%, CAUTION=TopK=15, DEFENSE=TopK=8 |
| 动态熔断 | 指数急跌15%/20日、融资余额周跌>10% |

---

## 四、架构 (Architecture)

### 4.1 系统总架构（七层）

```
┌─────────────────────────────────────────────────────┐
│  L0  风格择时门控 (regime.py / regime_router.py)      │
│       三通道 → GROWTH_OK/CAUTION/DEFENSE               │
│       控制 TopK、权重模式、L1 严格度、L5 折扣系数       │
├─────────────────────────────────────────────────────┤
│  预过滤器 (pre_filter.py)                             │
│       Layer 1: 基础清洗 (ST/金融/微型股)               │
│       Layer 2: Growth Signal Gate (多路径OR)           │
├─────────────────────────────────────────────────────┤
│  L1  排雷 Hard Gate (funnel.py)                       │
│       9项绝对红灯(单项淘汰) + 10项条件红灯(2项淘汰)     │
├─────────────────────────────────────────────────────┤
│  L2  护城河 (funnel.py)                               │
│       毛利率趋势 + 费用率杠杆 + 合同负债增长 + 研发强度  │
├─────────────────────────────────────────────────────┤
│  L3  资本效率 (funnel.py)                             │
│       ROIC/WACC + ROE + FCF + 有息负债率               │
├─────────────────────────────────────────────────────┤
│  L4  行业校准 (funnel.py)                             │
│       RPS60行业内Z-Score + 行业范式×生命周期权重        │
├─────────────────────────────────────────────────────┤
│  L5  预期差 (funnel.py)                               │
│       PEG/PE分位/增长加速度 (由 Regime 路由选择框架)     │
├─────────────────────────────────────────────────────┤
│  综合评分 (scorecard.py) → 排序输出                     │
└─────────────────────────────────────────────────────┘

旁路系统:
  CAPEX周期 (capex_cycle.py)       — 四象限产能周期定位
  增长持续性 (growth_persistence.py) — 飞轮概率评分
  增长探针 (growth_probes.py)       — 四维诊断(订单/CAPEX/毛利率/客户)
  利润质量 (profit_quality_probe.py) — 红灯归因分析
  卖出信号 (sell_signals.py)        — 五大类飞轮逆转检测
```

### 4.2 模块依赖图

```
main.py
  └─ backtest/engine.py
       ├─ universe.py           → 股票池
       ├─ trade_calendar.py     → 调仓日期
       ├─ signals.py            → Alpha信号(S3/S4/S5/S7)
       │    ├─ orthogonalizer.py → 分块对称正交化
       │    ├─ weights.py        → IR动态权重
       │    ├─ risk_factors.py   → 风险因子(Beta/Size/Vol/Illiquidity)
       │    └─ neutralizer.py    → 风险中性化
       ├─ valuation_filter.py   → 估值排雷(8条硬约束)
       ├─ screener.py           → 三维筛选器(景气度/壁垒/估值)
       │    └─ strategic_industries.py → 战略池overlay
       ├─ regime/detector.py    → Market Regime (BULL/STRUCT/BEAR)
       │    └─ regime/indicators.py → 五维度指标计算
       ├─ industry.py           → 申万行业映射
       ├─ diagnostics/attribution.py → Brinson归因
       └─ diagnostics/drawdown.py    → 回撤分析

growth_os/ (独立子系统 — 成长股深度分析)
  ├─ run_screen.py              → 批量筛选入口(多进程)
  ├─ batch_screen.py            → 批量筛选(单进程)
  ├─ report.py                  → 个股深度体检报告(Markdown)
  ├─ funnel.py                  → 五层漏斗核心
  ├─ lifecycle.py               → 生命周期判定+防抖
  ├─ scorecard.py               → 打分卡+综合评分
  ├─ regime.py                  → L0风格择时门控
  ├─ regime_router.py           → 个股Regime路由(状态机核心)
  ├─ regime_continuous.py       → 离散→连续仓位(0-100%)
  ├─ config.py                  → 框架参数+权重矩阵
  ├─ data.py                    → 数据加载层
  ├─ wacc.py                    → WACC计算
  ├─ capex_cycle.py             → CAPEX周期定位
  ├─ growth_probes.py           → 增长来源探针
  ├─ growth_persistence.py      → 增长持续性
  ├─ profit_quality_probe.py    → 利润质量归因
  ├─ sell_signals.py            → 卖出信号
  ├─ defense.py                 → 防御资产篮子
  ├─ pre_filter.py              → 预过滤器
  ├─ industry_paradigms.py      → 行业范式引擎(6范式)
  ├─ industry_indicators.py     → 行业领先指标(PMI/工业增加值等)
  ├─ visualization.py           → Q×V决策矩阵散点图
  ├─ pdf_download.py            → PDF财报下载
  ├─ pdf_extract.py             → PDF财报提取
  └─ pdf_data.py                → PDF数据整合

growth_source/ (增长来源分类器 — v2.3+)
  ├─ classifier.py              → 增长驱动力分类(tech_penetration等7类)
  ├─ cycle_state.py             → 周期状态判定
  ├─ industry_template.py       → 行业模板
  └─ position.py                → 持仓建议映射
```

### 4.3 数据流

```
T 月末
  │
  ├─ [数据加载]
  │   data_governance.py → 披露截止日过滤
  │   data.py → get_financial_snapshot() / get_quarterly_series()
  │
  ├─ [预过滤]
  │   pre_filter.py → 基础清洗 + Growth Signal Gate
  │
  ├─ [L0 市场状态]
  │   regime.py → A/B/C三通道 → GROWTH_OK/CAUTION/DEFENSE
  │
  ├─ [逐只分析] (多进程并行)
  │   lifecycle.py → 生命周期判定(含2期锁定防抖)
  │   funnel.py → L1排雷 → L2护城河 → L3资本效率 → L4行业校准 → L5预期差
  │   scorecard.py → 综合评分 + Regime路由
  │   capex_cycle.py → CAPEX周期定位
  │   growth_probes.py → 四维诊断
  │
  ├─ [排序输出]
  │   按 composite_score 排序 → Top N CSV
  │
  └─ [可选: 深度报告]
      report.py → Markdown 格式个股体检报告
```

---

## 五、创新点 (Innovations)

### 5.1 L0 风格择时门控 — 三通道连续信号

传统做法是离散 Regime 切换（牛/熊/结构），本项目首创**三通道连续信号 → 离散状态 + 连续仓位**双输出：

- **通道A**: 创业板/沪深300 63日动量（成长相对强度）
- **通道B**: 10Y国债 63日Δ（利率边际变化，阈值30bp）
- **通道C**: 创业板指 126日回撤（回撤熔断，阈值20%）

输出不仅有三态标签，还有 `ContinuousRegime` 类输出 0-100% 连续仓位。

### 5.2 个股 Regime 路由 — 6种评估框架

传统选股对所有股票用同一套打分公式。本项目将个股分为 6 种 Regime，每种走不同的评估框架：

| StockRegime | 估值框架 | 权重矩阵 | 决策模板 |
|------------|---------|---------|---------|
| 成长加速期 | PEG | 加速期权重 | 深度研究 |
| 成长成熟期 | PE分位 | 成熟期权重 | 加入观察池 |
| 导入期 | 增长加速度 | 导入期权重 | 成长待观察 |
| 周期过渡态 | PB-ROE | 周期权重 | 周期跟踪 |
| 周期出清 | PB-ROE | 防御权重 | 高风险观察池 |
| 商品驱动 | 不适用 | — | 一票否决 |

### 5.3 范式×生命周期 2D 权重矩阵

全球首创的 **二位权重矩阵**：行业范式（6种）× 生命周期阶段（4种）= 24 种权重模板（当前已实现 18 种）。

每种组合定义了 L1-L5 五层权重的不同分配，例如：
- 硬科技+导入期：L4(行业)权重 30% → 赛道选择重于个股壁垒
- 消费品牌+成熟期：L3(资本效率)权重 40% → 运营效率为王

### 5.4 分块对称正交化

标准正交化破坏所有因子间相关性。本项目**分块正交**：块内（S3+S4 动量组、S5+S7 质量组）EVD 正交消除共线，但块间保留原始相关结构 — 动量信号和质量信号之间的互补关系被保留。

### 5.5 CAPEX 周期四象限定位

将资本开支周期分为扩张期/危险区/收缩期/复苏期四个象限，结合 CAPEX/D&A 比（维护性 vs 扩张性）和在建工程信号做深度趋势分析。避免在周期顶部因"产能扩张"信号追高。

### 5.6 增长驱动力分类器（7 类标签）

```
tech_penetration  → 技术渗透型（光模块/芯片）— 高估值容忍
capacity_expansion → 产能扩张型（光伏/锂电）— 需CAPEX周期验证
brand_premium     → 品牌溢价型（白酒/消费）— 看毛利率韧性
drug_ramp         → 药物放量型（创新药）— 看管线+审批
share_gain        → 份额提升型（跨境电商）— 看竞争格局
cyclical_recovery → 周期恢复型 — 需确认拐点
quality_growth    → 品质成长型(后备) — 高ROIC+正增长未命中规则
```

### 5.7 LifecycleTracker — 带锁定期的生命周期防抖

传统做法每期重新判定生命周期，导致频繁切换。本项目引入 `LifecycleTracker`：新判定需要连续 2 期确认才生效，锁定期内用旧阶段。避免单季度数据波动导致的错误分类跳变。

### 5.8 三层数据治理消除前视偏差

```
优先级1: westock-data 实际公告日期 (InfoPublDate)
优先级2: 法定披露截止日 (Q1=4/30, Q2=8/31, Q3=10/31, Q4=次年4/30)
优先级3: 季度末保守假设
```

### 5.9 战略池 Overlay — 政策判断叠加

申万三级行业是描述性的，"核心战略/国产替代/新兴成长/绿色转型/数字经济"五大标签是判断性的。此文件独立维护，不与行业分类耦合。六大科技方向的 SW3 映射覆盖 80+ 细分行业。

---

## 六、功能清单 (Features)

### 6.1 核心选股功能

| 功能 | 入口 | 说明 |
|------|------|------|
| 全市场成长股筛选 | `growth_os/run_screen.py` | 多进程并行，Top N 输出 |
| 批量筛选 | `growth_os/batch_screen.py` | 单进程，完整漏斗打分 |
| 三维筛选器 | `screener.py` | 景气度/壁垒/估值三维 |
| 完整回测 | `main.py` | 2015-2024 全区间 |
| 切片回测 | `run_slice4.py / run_slice5.py` | 子区间验证 |
| 参数扫描 | `sweep.py` | TOP_N × PEG_MAX 网格 |

### 6.2 深度分析功能

| 功能 | 入口 | 输出 |
|------|------|------|
| 个股体检报告 | `growth_os/report.py` | Markdown 综合报告 |
| 决策矩阵图 | `growth_os/visualization.py` | Q×V 四象限散点图 |
| CAPEX周期定位 | `growth_os/capex_cycle.py` | 四象限 + CAPEX/D&A比 |
| 增长来源探针 | `growth_os/growth_probes.py` | 订单/CAPEX/毛利率/客户四维 |
| 利润质量归因 | `growth_os/profit_quality_probe.py` | L1红灯根因分析 |
| 卖出信号监控 | `growth_os/sell_signals.py` | 五大类飞轮逆转 |

### 6.3 风控功能

| 功能 | 机制 |
|------|------|
| 市场周期择时 | BULL/STRUCT/BEAR 三态 + 极端快速通道 |
| 防御模式 | 自动切中证红利40%+国债ETF40%+现金20% |
| 回撤预算 | 正常<15% / 预警15-25% / 临界>25% 三层响应 |
| 行业暴露控制 | BULL≤25% / STRUCT≤15% / BEAR≤10% |
| 估值排雷 | 8条硬约束（PEG/商誉/存贷双高/OCF等） |
| L1排雷 | 9绝对红灯 + 10条件红灯 |

### 6.4 诊断功能

| 功能 | 输出 |
|------|------|
| Brinson绩效归因 | 配置效应/选择效应/交互效应 |
| 回撤归因 | 最大回撤起止日、持续天数、恢复天数 |
| 因子相关性 | 因子间相关系数矩阵 |
| 主题动量 | 行业主题动量排名 |
| 探针准确率 | 四探针 vs 未来收益回测 |

### 6.5 数据维护功能

| 功能 | 脚本 |
|------|------|
| TDX财务刷新 | `tdx_financials.py` |
| 披露日历构建 | `build_disclosure_calendar.py` |
| 质量缓存重建 | `build_quality_cache.py` |
| 行业映射生成 | `sw_classify.py`（Sina源） |

---

## 七、具体使用方法 (Usage)

### 7.1 环境准备

```bash
cd /path/to/周期驱动因子系统
source .venv/bin/activate

# 确保数据就绪
ls data/cache/tdx_financials.csv      # 核心财务数据
ls data/cache/stock_list.csv          # 股票列表
ls data/cache/sw_stock_industry.csv   # 行业映射
ls data/cache/trade_calendar.csv      # 交易日历
```

### 7.2 个股深度体检报告

```bash
# 方式一：函数调用
python -c "from growth_os.report import generate_report; generate_report('300308', '20260526')"

# 方式二：模块入口
python -m growth_os.report 300308 20260527

# 输出: output/growth_report_{code}_{date}.md
```

报告包含：
- 综合评分 + 决策卡片
- L1-L5 五层诊断 + 红灯详情
- 生命周期判定 + 判定原因
- Regime 路由路径
- CAPEX周期位置
- 增长来源四探针
- 卖出信号检查
- 行业范式叙事
- 利润质量归因（如有红灯）

### 7.3 全市场扫描

```bash
# 全市场扫描，输出 Top 100
python -m growth_os.run_screen --date 20260519 --top 100

# 指定市值下限(亿元) + 并行worker数
python -m growth_os.run_screen --date 20260519 --top 50 --min-cap 50 --workers 8

# 单只股票分析
python -m growth_os.run_screen --date 20260519 --code 600519

# 输出: output/growth_pool_{date}.csv
```

### 7.4 批量筛选（完整漏斗）

```bash
python -m growth_os.batch_screen 20260331 50 50 500
#                                 日期    TopN 市值下限 候选池大小
```

### 7.5 完整回测

```bash
python main.py
# 输出: output/nav.csv (净值序列)
#       output/trades.csv (交易记录)
# 控制台: 年化收益/波动/夏普/最大回撤
```

### 7.6 参数扫描

```bash
python sweep.py
# 扫描 TOP_N ∈ {50,100,150} × PEG_MAX ∈ {2.0,2.5,3.0}
# 输出: output/sweep_results.csv
```

### 7.7 三维筛选器

```bash
python screener.py
# 基于 V4.2 三维框架（景气度/壁垒/估值）筛选
# 不生成组合，只输出排序清单供人工研究
```

### 7.8 数据维护

```bash
python tdx_financials.py              # 刷新通达信财务数据
python build_disclosure_calendar.py   # 重建披露日历
python build_quality_cache.py         # 重建质量因子缓存
```

### 7.9 可视化

```bash
python growth_os/visualization.py     # 生成 Q×V 决策矩阵散点图
python growth_os/regime_continuous.py # Regime 连续化离线验证
```

### 7.10 诊断分析

```bash
# 各诊断脚本独立运行
python diagnostics/attribution.py     # Brinson 绩效归因
python diagnostics/drawdown.py        # 回撤归因
python diagnostics/factor_corr.py     # 因子相关性
python diagnostics/themes.py          # 主题动量
```

---

## 八、Agent 驱动的 PDR 流程 (Preliminary Design Review)

### 8.1 PDR 定义与目标

PDR（Preliminary Design Review，初步设计评审）是本系统从 v3.0 演进到 v4.0 的关键关卡。目标：

1. 确认 v3.0 架构的技术可行性已经验证
2. 识别需要架构变更的设计缺陷
3. 为 v4.0 的 Sprint 20-21 制定可执行的技术路线图
4. 评估各模块的技术债务和风险

### 8.2 Agent 分工矩阵

建议使用 6 个专用 Agent 并行执行 PDR 各维度评审，然后由主线程合成最终报告：

```
PDR 总控 (主线程)
  │
  ├─ Agent 1: 架构完整性评审
  │   范围: 七层漏斗数据流、模块间接口、循环依赖检测
  │   工具: codegraph_impact + codegraph_callers
  │   输出: 架构图、接口契约缺口、耦合度评分
  │
  ├─ Agent 2: 数据治理评审
  │   范围: 前视偏差、披露日历覆盖率、财务数据质量、缓存一致性
  │   工具: Read data_governance.py + data.py + 缓存文件抽样
  │   输出: 数据质量报告、已知缺口列表
  │
  ├─ Agent 3: 因子有效性评审
  │   范围: S1-S7因子IC稳定性、因子衰减、正交化效果
  │   工具: Read signals.py + orthogonalizer.py + weights.py
  │         + diagnostics/factor_corr.py
  │   输出: 因子绩效矩阵、建议淘汰/新增因子
  │
  ├─ Agent 4: 风控完备性评审
  │   范围: Regime切换逻辑、极端行情覆盖、回撤预算、熔断机制
  │   工具: Read regime/ + defense.py + risk_factors.py
  │         + backtest/engine.py 风控部分
  │   输出: 风控缺口清单、压力场景覆盖矩阵
  │
  ├─ Agent 5: 代码质量评审
  │   范围: 复杂度、文件大小、重复代码、错误处理、类型安全
  │   工具: code-reviewer agent on growth_os/ + backtest/ + regime/
  │   输出: 代码异味清单、重构优先级
  │
  └─ Agent 6: 已知限制与路线图评审
      范围: ARCHITECTURE.md Known Limitations (L1-L14)
            CHANGELOG.md 已知问题
            docs/ 中所有 STATUS_*.md
      工具: Read docs/*.md
      输出: 限制项优先级排序、v4.0 准入条件检查
```

### 8.3 PDR 执行流程（分 4 阶段）

```
阶段 1: Scout (主线程，~5min)
  ├─ 1.1 列出所有模块文件 → codegraph_files
  ├─ 1.2 识别关键入口 → Read main.py, run_screen.py, batch_screen.py
  ├─ 1.3 检查 docs/ 最新状态 → Read CHANGELOG.md, STATUS_*.md
  └─ 1.4 生成 Agent 任务清单 → 分配至 6 个 Agent

阶段 2: Parallel Review (6 Agent 并行，~10min)
  ├─ Agent 1-6 各自执行评审任务
  └─ 各 Agent 输出结构化评审卡片

阶段 3: Synthesis (主线程，~5min)
  ├─ 3.1 合并 6 份评审报告
  ├─ 3.2 识别跨维度矛盾（如架构评审说某模块解耦好，代码质量评审说重复多）
  ├─ 3.3 交叉验证关键发现
  └─ 3.4 生成 PDR 最终报告

阶段 4: Report (主线程，~3min)
  ├─ 4.1 编写 PDR 结论文档 → docs/superpowers/pdr/
  ├─ 4.2 更新 Known Limitations 清单
  ├─ 4.3 提出 v4.0 架构变更建议
  └─ 4.4 Git commit PDR 报告
```

### 8.4 各 Agent 的评审维度与验收标准

#### Agent 1: 架构完整性

| 检查项 | 方法 | 通过标准 |
|--------|------|---------|
| 循环依赖 | `codegraph_impact` 遍历 | 0 循环依赖 |
| 接口契约 | 逐模块检查 `__init__.py` 导出 | 每个模块有明确公共 API |
| 数据流单向性 | 追踪 funnel→scorecard→output | 无反向依赖 |
| 配置集中度 | 检查 magic number 分布 | 90%+ 参数在 config/ |
| 模块内聚性 | 每个文件的功能数量 | 单文件 ≤ 5 个主要功能 |

#### Agent 2: 数据治理

| 检查项 | 方法 | 通过标准 |
|--------|------|---------|
| 前视偏差 | 抽样验证 filter_available_reports 调用 | 所有财务查询经过治理层 |
| 披露日历覆盖 | 检查 5508 只覆盖率 | ≥ 95% |
| 缓存一致性 | 检查 tdx_financials 与 financial_data 字段对齐 | 关键字段无冲突 |
| 数据新鲜度 | 检查最新缓存文件时间戳 | ≤ 90 天 |

#### Agent 3: 因子有效性

| 检查项 | 方法 | 通过标准 |
|--------|------|---------|
| IC 均值 | 遍历 S1-S7 的 IC 历史 | IR ≥ 0.3 的因子 ≥ 4 个 |
| IC 稳定性 | IC 标准差 | std(IC) ≤ 0.15 |
| 正交化效果 | VIF 计算 | 块内 VIF ≤ 3 |
| 因子衰减 | 滞后 IC 分析 | 6 个月后 IC 仍为正 |

#### Agent 4: 风控完备性

| 检查项 | 方法 | 通过标准 |
|--------|------|---------|
| Regime覆盖 | 所有历史月份有Regime判定 | 100% 覆盖 |
| 极端行情 | 检查 2015股灾/2018熊市/2020疫情/2024春节 | 正确触发DEFENSE |
| 回撤约束 | 回测最大回撤 vs 35% 预算 | ≤ 35% |
| 熔断响应时间 | 快速通道触发延迟 | ≤ 1 交易日 |

#### Agent 5: 代码质量

| 检查项 | 方法 | 通过标准 |
|--------|------|---------|
| 文件行数 | `wc -l *.py` | 单文件 ≤ 800 行（除 config） |
| 函数复杂度 | 人工审查 | 无 100+ 行单一函数 |
| 错误处理 | 搜索 bare except | 0 bare except |
| 类型注解 | 抽样检查 | 公共函数 80%+ 有类型注解 |
| 死代码 | 搜索未使用的 import/函数 | 0 已知死代码 |

#### Agent 6: 已知限制与路线图

| 检查项 | 方法 | 通过标准 |
|--------|------|---------|
| L1-L14 状态 | 逐条核实 | 所有 HIGH 项有明确计划 |
| Sprint 20 准入 | 检查静默期 2 周是否满足 | 已满足 |
| v4.0 依赖 | 确认 Sprint 20/21 数据验证 | 明确阻塞项列表 |
| 技术债务清单 | 汇总所有 TODO/FIXME/HACK | 排序 + 估时 |

### 8.5 PDR 输出物清单

```
docs/superpowers/pdr/
  ├── 2026-08-05-pdr-report.md        # PDR 总报告（主线程合成）
  ├── appendix-a-architecture.md      # Agent 1: 架构评审
  ├── appendix-b-data-governance.md   # Agent 2: 数据治理评审
  ├── appendix-c-factor-validity.md   # Agent 3: 因子有效性评审
  ├── appendix-d-risk-control.md      # Agent 4: 风控评审
  ├── appendix-e-code-quality.md      # Agent 5: 代码质量评审
  └── appendix-f-limitations.md       # Agent 6: 限制项与路线图
```

### 8.6 推荐的 Agent 启动命令序列

在 Claude Code 会话中，可以通过以下方式启动 PDR：

```
# 阶段 1: Scout（主线程执行）
"用 codegraph 全面扫描项目结构，列出所有模块、入口点、关键依赖"

# 阶段 2: 并行启动 6 个 Agent
"帮我对这个项目做 PDR（初步设计评审），用 6 个 agent 并行评审：
1. code-reviewer agent 评审 growth_os/ 下全部代码质量
2. 安全审计 agent 评审风控体系（regime/, defense.py, risk_factors.py）
3. 测试 agent 评审因子有效性（signals.py, weights.py, diagnostics/）
4. 通用 agent 评审数据治理（data_governance.py, data.py, 缓存机制）
5. 通用 agent 评审架构完整性（模块依赖图、接口契约、循环依赖）
6. 通用 agent 评审已知限制和路线图（docs/ 下全部 md）"

# 阶段 3: Synthesis
"合成 6 份评审报告为一份 PDR 总报告，识别跨维度矛盾，输出到 docs/superpowers/pdr/"

# 阶段 4: Report
"根据 PDR 结果更新 Known Limitations 清单，提出 v4.0 架构变更建议，commit"
```

---

## 九、参考资料 (References)

### 9.1 项目内部文档

| 文档 | 路径 | 内容 |
|------|------|------|
| 架构文档 | `docs/ARCHITECTURE.md` | v2.0 六层漏斗架构、因子体系、风控体系 |
| 技术规格书 | `docs/README.md` | V4.2 最终定稿版完整技术规格 |
| 变更日志 | `docs/CHANGELOG.md` | Sprint 17-19 详细变更记录 |
| 数据清单 | `docs/DATA_INVENTORY.md` | 19个缓存文件、数据源、消费者 |
| 因子手册 | `docs/factor_handbook.md` | 各因子定义、计算方式、使用场景 |
| 参数手册 | `docs/params_manual.md` | 全局可配置参数说明 |
| 叙事模板 | `docs/narrative_templates.md` | 各行业范式的叙事框架 |
| 状态报告 | `docs/STATUS_20260530.md` | 2026-05-30 系统状态 |
| 状态报告 | `docs/STATUS_20260531.md` | 2026-05-31 系统状态 |
| 观察清单 | `docs/WATCHLIST.md` | 战略性标的跟踪清单 |
| 理论文档 | `docs/theory-market-information-geometry.md` | 市场信息几何学理论 |
| 基线重置 | `docs/v1.0-baseline-reset-memo.md` | v1.0 基线重建备忘 |
| 报告评审 | `docs/report_review_20260527.md` | 2026-05-27 报告评审 |
| 报告评审 | `docs/report_review_300274_20260527.md` | 个股报告评审 |
| 矩阵图 | `docs/"核心驱动力-周期状态-持仓策略"矩阵图.png` | 持仓策略矩阵 |
| 通达信字段 | `docs/通达信专业财务数据项.xls` | TDX 字段映射 |
| SW行业对照 | `docs/sw_index_third_cons.csv` | 申万三级行业成分股 |

### 9.2 核心模块源码

| 模块 | 路径 | 关键功能 |
|------|------|---------|
| 回测引擎 | `backtest/engine.py` | 等权回测、Brinson归因、回撤分析 |
| 五层漏斗 | `growth_os/funnel.py` | L1-L5 全部打分逻辑 |
| Regime门控 | `growth_os/regime.py` | L0 三通道风格择时 |
| Regime路由 | `growth_os/regime_router.py` | 个股6Regime状态机 |
| 连续Regime | `growth_os/regime_continuous.py` | 0-100% 连续仓位 |
| 生命周期 | `growth_os/lifecycle.py` | 四阶段判定+LifecycleTracker防抖 |
| Alpha信号 | `signals.py` | S3/S4/S5/S7 因子计算 |
| 三维筛选 | `screener.py` | 景气度/壁垒/估值筛选+战略池overlay |
| 综合评分 | `growth_os/scorecard.py` | GrowthScorecard+composite计算 |
| 行业范式 | `growth_os/industry_paradigms.py` | 6范式×行业映射 |
| CAPEX周期 | `growth_os/capex_cycle.py` | 四象限CAPEX定位 |
| 增长探针 | `growth_os/growth_probes.py` | 订单/CAPEX/毛利率/客户四维 |
| 增长分类器 | `growth_source/classifier.py` | 7类增长驱动力 |
| 卖出信号 | `growth_os/sell_signals.py` | 五类飞轮逆转检测 |
| 风控因子 | `risk_factors.py` | Beta/Size/Vol/Illiquidity |
| 正交化 | `orthogonalizer.py` | 分块对称EVD正交化 |
| IR权重 | `weights.py` | 滚动IR动态权重 |
| 数据治理 | `data_governance.py` | 披露截止日前视偏差消除 |
| 预过滤器 | `growth_os/pre_filter.py` | 两层预过滤 |
| 估值排雷 | `valuation_filter.py` | 8条硬约束 |
| 行业映射 | `industry.py` | 申万L1/L2/L3映射 |
| 战略行业 | `config/strategic_industries.py` | 国家战略方向overlay |
| 防御资产 | `growth_os/defense.py` | 中证红利+国债ETF+现金 |
| Market Regime | `regime/detector.py` | 五维度BULL/STRUCT/BEAR判定 |
| 行业指标 | `growth_os/industry_indicators.py` | PMI/工业增加值等产业数据 |
| 可视化 | `growth_os/visualization.py` | Q×V决策矩阵散点图 |

### 9.3 外部依赖与数据源

| 依赖 | 用途 |
|------|------|
| akshare 1.18.63 | A股在线数据API（日线/指数/宏观） |
| pytdx | 通达信本地数据文件解析 |
| pandas 2.2.2 | 数据处理核心 |
| numpy 1.26.4 | 数值计算 |
| scipy 1.17.1 | 统计检验(Spearman/EVD) |
| loguru | 结构化日志 |
| matplotlib | 可视化 |
| Sina 财经 | 交易日历 + 申万行业分类 |
| westock-data | 实际公告日期 |
| 腾讯行情 | 个股日线数据源 |
| 中国10Y国债 | 利率通道输入 |
| 中证红利000922 | 防御篮子 |
| 国债ETF 511010 | 防御篮子 |

### 9.4 关键配置文件

| 文件 | 关键参数 |
|------|---------|
| `config/params.py` | 初始资金/交易成本/仓位上限/Regime阈值/Alpha阈值/估值排雷 |
| `growth_os/config.py` | 生命周期判定阈值/权重矩阵(3种)/Regime权重(2种)/范式×生命周期2D矩阵(18种) |
| `config/strategic_industries.py` | 六大科技方向×SW3行业映射 + 五大战略标签 |
| `config/tdx_fieldmap.py` | 通达信100+字段→标准名称映射 |

### 9.5 诊断输出物

| 输出 | 路径 |
|------|------|
| 净值序列 | `output/nav.csv` |
| 交易记录 | `output/trades.csv` |
| 扫描结果 | `output/growth_pool_{date}.csv` |
| 个股报告 | `output/growth_report_{code}_{date}.md` |
| 参数扫描 | `output/sweep_results.csv` |
| 因子相关性 | `diagnostics/factor_corr_YYYYMM.csv` |
| 主题动量 | `diagnostics/theme_momentum_YYYYMM.csv` |
| Q×V矩阵图 | `output/growth_pool_{date}_matrix.png` |

---

## 附录：关键术语表

| 术语 | 英文 | 说明 |
|------|------|------|
| 漏斗 | Funnel | 逐层过滤框架，L0→L1→L2→L3→L4→L5 |
| 排雷 | Hard Gate | L1层，19项红灯检验（9绝对+10条件） |
| 护城河 | Moat | L2层，毛利率趋势+费用率杠杆+合同负债+研发 |
| Regime | Regime | 市场/个股状态分类，决定权重和估值框架 |
| 范式 | Paradigm | 行业评估框架（硬科技/软件/医疗/消费/工业/通用） |
| 生命周期 | Lifecycle | 导入期/加速期/成熟期/衰退期 |
| CAPEX周期 | CAPEX Cycle | 扩张期/危险区/收缩期/复苏期 |
| 探针 | Probe | 增长来源四维诊断（订单/CAPEX/毛利率/客户） |
| 打分卡 | Scorecard | 综合评分数据结构 |
| 前视偏差 | Look-ahead Bias | 使用未来数据评估过去决策的错误 |
| 正交化 | Orthogonalization | 消除因子间共线性 |
| 滞回 | Hysteresis | 状态切换的防抖机制 |
| 冷启动 | Cold Start | 无历史数据时的等权默认策略 |
