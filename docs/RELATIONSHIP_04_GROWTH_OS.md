# RELATIONSHIP_04_GROWTH_OS — 两系统架构边界（冻结）

**日期**: 2026-09-03
**状态**: 架构冻结 — Growth OS(认知) 与 04 Alpha Trader(行动) 分层明确
**核心原则**: 不互相污染评分。04 不进入 Growth OS 的 L/E/P；Growth OS 不输出买卖点。

---

## 一、架构总览（共享信息基础设施）

```
                Internet / Data Sources
                       ↓
        ┌──────────────────────────────┐
        │   XIS 信息信号基础设施         │
        │  (新闻/公告/政策/调研/产业链)   │
        │  Event Normalization → E1-E18 │
        └──────────────┬───────────────┘
                       ↓
        ┌──────────────┴──────────────┐
        ↓                             ↓
   Growth OS                     04 Alpha Trader
   研究什么？                     什么时候交易？
   ─────────                     ─────────────
   L/E/P 状态                    EIS/OQS/ERS/TQS
   Thesis/Ledger                 G1-G7 分类
   长期假设                      交易执行/双止损
   季度/月周期                    日/周/月周期
        ↓                             ↓
      长期判断                       短期执行
        └──────────────┬──────────────┘
                       ↓
                  Review DB
                       ↓
              T+30/T+90 复盘 (共享学习)
```

## 二、职责边界（谁负责什么 / 谁不能干什么）

### Growth OS（认知系统）
- ✅ 公司质量 / 长期逻辑 / Thesis / Ledger / 研究优先级（L/E/P）
- ✅ 5000→50 研究池压缩、Memo、证伪条件
- ❌ 买卖点、仓位、止损（不自动交易）
- ❌ 综合评分（历史验证: RPI 坍缩教训）

### 04 Alpha Trader（行动系统）
- ✅ 事件机会识别（E1-E18）、交易窗口（Entry Structure）、风险管理（Risk Unit/双止损）
- ✅ 短中期 Alpha（1日~6月）、G0-G7 分类、Forward EPS Test
- ❌ 判断"伟大公司"、建立长期认知（那是 Growth OS 的职责）

## 三、唯一接口（三个）

| 接口 | 方向 | 内容 |
|---|---|---|
| 接口1 股票池 | Growth OS → 04 | Core Research / Watchlist / Shadow 三级池（候选输入） |
| 接口2 事件流 | XIS → 两个系统 | E1-E18 规范化事件（共用，不重复采集） |
| 接口3 复盘数据 | 04 → Growth OS | 交易结果回填 → 校准长期 Thesis（"判断对但交易败"归因） |

## 四、禁止事项（防边界污染）

1. ❌ X 事件不直接改 Growth OS 的 L/E/P 状态
2. ❌ 04 的 OQS/ERS/TQS 不进入 Growth OS 研究标签
3. ❌ Growth OS 不产生买卖点/仓位建议
4. ❌ 同一条事件不重复计分（04 计分与 Growth OS 影响评估互不引用）
5. ✅ X 事件只触发: 研究层更新（Ledger 记录 / Thesis 检查请求）

## 五、数据流向

```
XIS → data/events/            (共享事件库, 已建)
Growth OS → data/ledger/      (判断/Thesis, 已建)
04 → data/trades/ (待建)      (执行记录: entry/exit/stop/result)
Review: 04 交易结果 + Growth OS 判断 同库复盘 (T+30/90)
```

## 六、本架构冻结的意义

- 给未来自动 Agent 划"权限边界"：Agent 可以采集/分类/提醒，但**无权改变研究状态或产生交易动作**
- 防止"信息越强 → 系统越被新闻带偏"（边界比爬虫重要）
- 两个系统各自进化, 通过三个接口 + 共享数据解耦

## 七、后续（按冻结纪律）

1. ⬜ EVENT_THESIS_MAPPING_PROTOCOL.md（X 接口细化）
2. ⬜ event_scan 升级 E1-E18 分类词库
3. ⬜ 运行 30 天积累 → T+30 决定是否需要 X v1 影响模型
