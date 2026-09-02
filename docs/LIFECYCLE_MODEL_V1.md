# Lifecycle Model v1 — 生命周期状态机（冻结版）

**状态**: v1.0 冻结（2026-09-02）
**实证依据**: Discovery Audit / State Machine Audit / Industry Adaptive Audit / L5 Recovery v2 / 迁移概率矩阵

---

## 一、状态定义（内部 L0-L5 → 业务语言）

| 内部 | 业务语言 | 判定条件 | 研究优先级 | Radar |
|---|---|---|---|---|
| L0 | Ignore | Discovery 低 或 探针数据不足 | IGNORE | watch |
| L1 | Early Discovery | Discovery ≥0.5 + RPS <40 | **A** | growth_radar |
| L2 | Confirmation | Discovery ≥0.5 + RPS 40-70 | B | growth_radar |
| L3 | Consensus | Discovery ≥0.5 + RPS ≥70 | C | watch |
| L5 | Recovery Watch | L5 引擎四层判定通过 | **A** | recovery_radar |

## 二、行业范式参数化（v2 实证）

| 范式 | 行业（SW1） | 规则 |
|---|---|---|
| cycle_manufacturing | 有色/化工/机械/钢铁/煤炭/石化/建材 | L1 优先（L1-L0 = +5.5pp） |
| consumer | 医药/食品/家电/纺织/农业/社服/美容 | L1 弱有效（+2.8pp） |
| defensive | 银行/非银/公用/交运/地产 | L2 确认优先（+2.2pp） |
| tech_growth | 电子/通信/计算机/传媒/军工 | **探针状态机不适用** → IGNORE |

## 三、L5 错杀恢复（四层判定）

```
L5 = 历史确认（RPS曾≥70 或 历史L2/L3）
   ∩ 错误定价（60日<-20% / 高点回撤<-25% / RPS崩塌>30 / PE分位压缩，三选二）
   ∩ 基本面未破坏（探针red≤1 + 收入未加速恶化 + 利润未连续恶化）
   ∩ 行业范式 ∈ {cycle_manufacturing, consumer}
```

输出: L5-A（基本面全绿，恢复确定性 55%）/ L5-B（需人工，收益弹性 17.1%）

**实证**: 恢复率 50.2%（Train 50% / Test 51%）、错误率 8.7%、Recovery Efficiency 53%

## 四、状态迁移概率（研究优先级依据）

| 事件 | 概率（4个月） | 研究含义 |
|---|---|---|
| L1 → L2/L3 | 46.3% | 值得跟踪 |
| L3 → L5 | 16.7% | 持有观察 |
| L5 → L3 | 25.1% | 值得研究 |
| L5 → L2/L3（8个月） | 41.1% | 恢复窗口 |
| L0 → 维持 | 76.5% | 不投入 |

## 五、设计原则（不可违反）

1. **Lifecycle ≠ Score**：状态标签不进入 composite/score（正交，防幻觉回归）
2. **双轨输出**：原排序不变，标签并列
3. **先验证后接入**：任何状态修改需 Train/Test 分离验证
4. **指标纪律**：评价函数错误可能判死有效模块（L5 26.7%→50.2% 教训）
