# Slice 3: Alpha 信号层 设计文档

**日期**: 2026-05-15
**关联**: V4.2 周期驱动三因子动态选股系统
**基于**: Slice 1 等权基准（13.44% 年化，-55.56% 回撤）+ Slice 2 周期判定（已实现，不做仓位调节）
**目标**: 验证"Alpha 信号选股能否跑赢全市场等权基准"

---

## 1. 目标

在 Slice 1 全市场等权基础上，用 4 个 Alpha 信号（S3 动量 + S4 行业共振 + S5 盈利稳定 + S7 现金流质量）精选前 100 只股票，等权配置。对比基准验证 Alpha 增益。

## 2. 设计原则

- **Regime 代码保留但不驱仓**：Slcie 2 的 `detect_regime` 作为元数据标签，不强制仓位缩放
- **行业内 Z-Score**：所有信号在申万一级行业内标准化，消除行业间系统性偏差
- **NaN 宽容**：缺信号的股票不淘汰，仅用其非 NaN 因子参与计算
- **等权打分法**：Alpha 排名前 100 等权，无优化器——纯验证信号质量

## 3. 架构

```
新增:
industry.py           # 申万2024一级行业映射
signals.py            # S3/S4/S5/S7 + Alpha合成

修改:
backtest/engine.py    # 全市场等权 → Top100 Alpha等权
```

数据流：
```
industry.py (code → SW行业)
    │
    ├─→ S4 (行业聚合: 动量/广度/新高)
    ├─→ S3 (行业内 RPS60)
    ├─→ S5 (行业内 ROE稳定性)
    └─→ S7 (行业内 现金流质量)
    │
signals.py → Alpha_Score (Z-Score均值)
    │
engine.py → Top 100 等权
```

## 4. 模块详设

### 4.1 industry.py — 申万行业映射

**数据源**：`ak.index_stock_cons(symbol=sw_code)` — Sina 源，已验证可用

**SW 2024 31 行业代码**：

```python
SW_INDUSTRIES = {
    "801010": "农林牧渔", "801020": "煤炭", "801030": "化工",
    "801040": "钢铁", "801050": "有色金属", "801080": "电子",
    "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服饰",
    "801140": "轻工制造", "801150": "医药生物", "801160": "公用事业",
    "801170": "交通运输", "801180": "房地产", "801200": "商贸零售",
    "801210": "社会服务", "801230": "综合", "801710": "建筑材料",
    "801720": "建筑装饰", "801730": "电力设备", "801740": "国防军工",
    "801750": "计算机", "801760": "传媒", "801770": "通信",
    "801780": "银行", "801790": "非银金融", "801880": "汽车",
    "801890": "机械设备", "801960": "石油石化", "801970": "环保",
    "801980": "美容护理",
}
```

**函数**：
```python
def get_sw_industry() -> dict[str, str]:
    """返回 {stock_code: sw_industry_name} 映射。
    缓存优先(data/cache/sw_industry_map.csv)，
    首次调用遍历31行业获取成分股。
    """
```

**缓存格式**：`code,industry`

### 4.2 signals.py — S3 个股动量

**数据源**：已缓存的个股日线 `data/cache/daily_prices/{code}.csv`

**判定条件（全部满足才输出有效值）**：

| # | 条件 | 计算 |
|---|------|------|
| 1 | RPS60 ≥ 65 | 60 日累计收益的行业内百分位 |
| 2 | close > MA50 | 最新收盘价 vs 50 日均线 |
| 3 | MA50 > MA200 | 中期均线 > 长期均线 |
| 4 | 振幅可控 | 近 30 日 (high-low)/close 均值 < 历史 90% 分位 |
| 5 | 持续强势 | 近 60 日中有 ≥ 30 日 close > MA50 |

**输出**：`S3 = Z(RPS60)`，行业内标准化，缩尾 1%/99%。条件不满足 → NaN。

### 4.3 signals.py — S4 行业趋势共振

**数据源**：个股日线 + `industry.py` 行业映射

**三个条件 AND 组合**：

| 条件 | 计算 | 阈值 |
|------|------|------|
| 行业动量 | 行业内个股 60 日收益中位数，排名全 31 行业 | 前 40%（约前 12 名） |
| 行业广度 | 行业内近 20 日上涨个股占比 | > 50% |
| 行业新高 | 行业内距 52 周高点 < 5% 的个股占比 | > 该行业过去 5 年中位数 |

**三者同时满足** → `S4 = 0.7 × Z(行业涨幅) + 0.3 × Z(行业广度)`。
任一不满足 → 该行业内所有股票的 S4 = NaN。

### 4.4 signals.py — S5 盈利稳定性

**数据源**：`ak.stock_financial_analysis_indicator(symbol, start_year)`，取 `加权净资产收益率(%)`

**计算**：
- 每只股票：近 3 年（12 个季度）加权 ROE 的标准差
- 行业内百分位反向 Z-Score：`S5 = -Z(ROE_std)`
- 负值（波动大于行业均值）为负分，正值（波动小于行业均值）为正分
- 不足 8 个季度数据 → NaN

**简化**：不做重大重组剔除、不做审计非标检查（留后续）

### 4.5 signals.py — S7 现金流质量

**数据源**：同上函数，取 `经营现金净流量对销售收入比率(%)`

**计算**：
- `S7 = Z(经营现金流/营收)`，行业内标准化，缩尾 1%/99%
- 负值或 NaN → NaN

### 4.6 Alpha 合成

```python
def compute_alpha(t_date: str, codes: list[str]) -> dict[str, float]:
    """
    返回 {code: alpha_score}。
    Alpha = 非NaN因子的等权平均，行业内有至少1个非NaN因子才输出。
    """
```

每个 signal 函数签名：`signal_fn(t_date, codes, industry_map) -> pd.Series`

### 4.7 backtest/engine.py 修改

调仓逻辑中，将：

```python
target_weights = {code: min(1.0 / n, MAX_SINGLE_WEIGHT) for code in target_codes}
```

改为：

```python
alpha_scores = compute_alpha(t_date, target_codes)
ranked = [c for c, s in sorted(alpha_scores.items(), key=lambda x: x[1], reverse=True)]
top_n = min(len(ranked), 100)
target_weights = {c: min(1.0 / top_n, MAX_SINGLE_WEIGHT) for c in ranked[:top_n]}
```

Regime 仓位缩放移除（POSITION_CAP 导入可保留但不使用）。

## 5. 项目目录（更新后）

```
周期驱动因子系统/
├── main.py
├── trade_calendar.py
├── universe.py
├── industry.py              # 新增
├── signals.py               # 新增
├── regime/                  # 保留，不做仓位调节
│   ├── __init__.py
│   ├── indicators.py
│   └── detector.py
├── backtest/
│   ├── __init__.py
│   └── engine.py            # 修改：全市场→Top100
├── config/
│   ├── __init__.py
│   └── params.py
└── output/
```

## 6. 成功标准

- [ ] industry.py 生成 31 行业映射，覆盖 > 4000 只股票
- [ ] 每个信号函数独立可运行，输出有效 Z-Score
- [ ] S3 约 10-15% 股票有效（动量精选）
- [ ] S4 约 30-40% 股票有效（行业共振精选）
- [ ] 回测 2015-2024 无异常，Top100 组合 ≥ 15 只
- [ ] 夏普/回撤 vs Slice 1 基准有改善趋势（不要求大幅超越，因 Slice 4 还有优化器）

## 7. 已知局限

- S5 不做重大重组/审计非标检查
- 行业映射为 2021 版 SW 代码（31 个），非 2024 最新版（差异很小）
- Alpha 合成为简单等权平均，不做 IC_IR 动态权重（Slice 4）
- 无风险中性化、无正交化（Slice 4）
- 无估值排雷（Slice 4）
- 无优化器，纯打分选股（Slice 4）
