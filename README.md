# 周期驱动因子系统

A股主动基本面景气策略选股系统。目标函数：最大化 Calmar（约束：回撤 ≤ 35%）。

## 两条筛选链路

| | `screener.py` | `growth_os/run_screen.py` |
|---|---|---|
| 定位 | 轻量扫描 — 发现"市场在奖励什么" | 深度诊断 — 验证"值不值得买" |
| 框架 | 三维：景气度 × 壁垒 × 估值 | 六层漏斗：L1→L5 分层诊断 |
| 输出 | Top 200 CSV + 拐点模式 Top 50 | Top N CSV + 归因卡片 + 仓位建议 |
| 速度 | ~7 分钟 | ~19 分钟 |

**两者交集是最值得重点研究的标的。**

## 快速开始

```bash
source .venv/bin/activate

# 轻量扫描
python -m screener                          # 默认：Top 200
python -m screener growth                   # 拐点爆发模式 Top 50

# 深度诊断
python -m growth_os.run_screen --top 20     # 全市场筛选 + 六层漏斗

# 个股体检
python -m growth_os.run_screen --code 300308

# 回测
python main.py                              # 完整回测 2015-2024
```

## 项目结构

```
screener.py                  # 轻量扫描器（三维框架）
signals.py                   # Alpha信号：S1-S7
valuation_filter.py          # 估值排雷（8条硬约束）
growth_os/                   # 核心引擎
├── run_screen.py            # 深度诊断入口（六层漏斗）
├── pre_filter.py            # 预过滤器（A/B/C/D成长路径门控）
├── funnel.py                # 漏斗打分
├── scorecard.py             # GrowthScorecard
├── report.py                # 个股体检报告
├── regime_router.py         # Regime路由
└── data.py                  # 数据加载
regime/                      # 市场状态判断
backtest/                    # 回测引擎
config/
├── params.py                # 全局参数
└── strategic_industries.py  # 六大方向 × 申万三级行业映射（人工维护）
diagnostics/                 # 诊断分析
output/                      # 输出结果
data/cache/                  # 数据缓存
```

## 核心概念

### 六大战略方向

系统通过 `config/strategic_industries.py` 维护与 [streamlit项目01](https://github.com/nayiahul/Cyclical-Driver-System) 同步的**六大科技方向 × 申万2021版三级行业映射**：

1. AI全产业链（算力基建 + 大模型 + 智能终端）
2. 电力与新能源（能源底座）
3. 芯片半导体（国产替代）
4. 机器人与高端制造
5. 生命科学 + AI
6. 商业航天与低空经济

启动时自动校验映射完整性，覆盖缺口在日志中告警。

### 因子体系

| 因子 | 维度 | 说明 |
|------|------|------|
| S1 | 景气度 | 利润加速度：近3季扣非净利润同比线性回归，斜率>0且R²>0.6 |
| S2 | 景气度 | 产能扩张：合同负债TTM yoy + CAPEX yoy |
| S5 | 壁垒 | 盈利稳定性：近12季ROE标准差，行业内反向Z-Score |
| S7 | 壁垒 | 现金流质量：经营现金流/营收，行业内Z-Score |
| RPS60 | 景气度 | 60日相对价格强度，行业内百分位 |

### 战略池分层

六大方向核心行业享受：
- **独立因子权重**：moat 降 10pp，momentum 提 5pp
- **S1 阈值放宽**：R² 0.6→0.4
- **保底名额**：Top N 中 ≥40% 来自战略池
- **行业指数RPS**：真空期混入个股RPS，降低纯价格动量依赖

## 配置维护

`config/strategic_industries.py` 是系统唯一的"主观判断"层。维护指南在文件头部。运行 `python -m screener` 时自动检查：
- 命名漂移（申万改版）
- 覆盖缺口（候选池中未映射的疑似相关行业）
