# L5 Data Readiness Audit — 错杀恢复引擎字段盘点

**日期**: 2026-09-01（Step 2.1 实勘）
**结论**: **数据就绪度 ~95%**（原预估 80-85%），主要缺口已消除

---

## 一、字段矩阵（实勘结果）

| 模块 | 字段 | 状态 | 来源 | 备注 |
|---|---|---|---|---|
| **Layer 1 历史确认** | 历史 L2/L3 状态 | ✅ | state_machine 输出（12 采样日） | 已有 |
| | RPS 历史/最高 RPS | ✅ | compute_rps60（可重算任意 t） | 可生成 |
| | 历史涨幅 | ✅ | STOCKS_DIR 价格 | 可生成 |
| **Layer 2 错误杀跌** | 60/120 日收益 | ✅ | 价格（as_of 截断） | 可生成 |
| | 回撤 drawdown | ✅ | 价格 | 可生成 |
| | **PE 历史序列** | ✅ **（原以为缺口）** | **价格文件 `peTTM` 列（每日）** | **重大发现：无需新数据源** |
| | PE 历史分位 | ✅ 可构建 | peTTM 序列滚动分位 | `growth_os/get_pe_ttm` 已有单点实现 |
| | RPS collapse | ✅ | RPS 序列 | 可生成 |
| **Layer 3 基本面** | 订单/CAPEX/毛利探针 | ✅ | growth_probes（green/yellow/red） | 已有 |
| | 收入 YoY | ✅ | tdx `revenue_yoy` | 已有 |
| | 利润趋势 | ✅ | tdx `net_profit_yoy` / `operating_profit_yoy` / `deducted_profit_yoy` | 已有 |
| | 毛利率趋势 | ✅ | tdx `gross_margin`（12 季序列） | 已有 |
| | 行业范式 | 🟡 部分 | industry_paradigms.py（SW3 级范式定义） | 有定义，无"行业周期状态"实时判定 |
| | CAPEX 周期 | 🟡 部分 | capex_cycle.py | 有个股级，无行业级 |

## 二、三个关键问题的回答

### Q1：PE 历史分位是否已有？——✅ 已解决（意外发现）

**价格文件自带每日 `peTTM` 列**（腾讯源），`get_pe_ttm(code, t_date)` 已实现单点读取（且做了 as_of 截断）。

```python
# PE 历史分位构建（L5 Layer 2 用）
df = MarketData.as_of(code, t_date)
pe_series = df["peTTM"].dropna()
current_pe = pe_series.iloc[-1]
pct = (pe_series < current_pe).mean()  # 当前 PE 历史分位
# 估值压缩 = 过去 250 日分位高 → 当前分位低
```

**影响**: 原预估的最大缺口不存在——PE 压缩判定可直接构建，无需新增数据源。

### Q2：L5 是否限制行业？——✅ 建议 v1 只开放周期制造 + 消费

- `industry_paradigms.py` 已有 SW3 级范式定义（`get_industry_paradigm(industry_l3)`）
- 与 L1 证据一致：周期制造 +5.5pp 有效 / tech_growth 无效
- v1 限制：`PARADIGM ∈ {cycle_manufacturing, consumer}`；tech_growth/defensive 暂不开放

### Q3：L5 输出定位？——✅ Research Priority，非评分

已定：输出 `{state: "L5", priority: "A", reason, risk}`，零评分影响。

## 三、剩余小缺口（不阻塞 v1）

| 缺口 | 影响 | 处理 |
|---|---|---|
| 行业周期状态实时判定（库存/价格周期） | L5 的"行业未衰退"条件只能用范式粗筛 | v1 用范式白名单代替；v2 再建设 |
| 部分股票 peTTM 缺失（早于 2021 或退市） | PE 压缩判定缺样本 | 用 pbMRQ 兜底或跳过 PE 条件（L5 核心是"经营未坏+杀跌"，PE 仅辅助） |
| 历史状态序列仅 12 采样日（季度级） | "过去被确认"判定粒度粗 | v1 用"RPS 曾 ≥70"代替（日级可算） |

## 四、结论

**L5 v1 数据就绪度 95%**，三个判定层全部可构建且 PIT 安全：

```
L5 = 历史确认（RPS曾≥70 或 历史L2/L3）
   ∩ 错误杀跌（60日急跌 + RPS collapse + PE分位压缩[可选]）
   ∩ 基本面未破坏（探针非red + 收入/利润未连续恶化）
   ∩ 行业范式 ∈ {cycle_manufacturing, consumer}
```

**唯一实质性待办**：开发 `growth_os/l5_recovery.py`（Step 3）——数据侧无阻塞。
