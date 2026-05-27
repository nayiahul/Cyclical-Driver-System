# 周期驱动因子系统

A股主动基本面景气策略选股系统。六层漏斗：股票池 → 排雷 → 因子评分 → Regime → 行业约束 → 排序输出。目标函数最大化 Calmar（回撤 ≤ 35%）。

## 项目结构

```
growth_os/     # 核心引擎 (probes/regime/funnel/backtest/scorecard)
diagnostics/   # 诊断分析 (attribution/drawdown/factor_corr/themes)
regime/        # 市场状态判断
backtest/      # 回测引擎
config/        # 配置文件
docs/          # 架构文档 / Factor Handbook / 参数手册
output/        # 输出结果
```

## 环境

- Python 3.x, venv 在 `.venv/`
- 依赖: pandas, numpy, akshare, pytdx, loguru
- 数据缓存: `data/cache/` (gitignored, 但 tdx_financials.csv 被跟踪)

## 开发约定

- 没有测试套件，通过 diagnostics/ 下的诊断脚本验证
- 配置文件在 config/params.py
- 入口: main.py → backtest/engine.py
- 单股票分析: growth_os/run_screen.py

## 运行方式

### 1. 个股深度体检报告

```bash
source .venv/bin/activate
python -c "from growth_os.report import generate_report; generate_report('300308', '20260526')"
```

输出 `output/growth_report_{code}_{date}.md`，包含综合评分、决策卡片、L1-L5 分层诊断、轨迹层、增长来源探针。

### 2. 批量筛选 + 回测

```bash
source .venv/bin/activate
python main.py                         # 完整回测 2015-2024 → output/nav.csv
python run_slice4.py                   # 切片4回测
python run_slice5.py                   # 切片5回测
python growth_os/run_screen.py         # 全市场扫描 → 观察池 CSV
python growth_os/batch_screen.py       # 批量筛选 → Top N CSV
python screener.py                     # 三维筛选器（景气度/壁垒/估值）
python sweep.py                        # 参数网格扫描 (TOP_N × PEG_MAX)
```

### 3. 工具/诊断/数据维护

```bash
source .venv/bin/activate
python growth_os/visualization.py      # Q×V 决策矩阵散点图
python growth_os/regime_continuous.py  # Regime 连续化离线验证
python tdx_financials.py               # 通达信财务数据刷新
python build_disclosure_calendar.py    # 披露日历构建
python build_quality_cache.py          # 质量因子缓存重建
```
