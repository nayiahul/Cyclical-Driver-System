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
