# Growth OS Runtime Daily Checklist v1 — 每日执行卡

**运行期**: 2026-09-03 ~ 2026-10-02（30 天真实运行）
**冻结版本**: Growth OS v3.5 + XIS v1 + 04 Alpha v3 + Golden Pit v1 + COHR Monitor v1
**核心目标**: 积累 100 条人机共同判断（非找买卖机会）

---

## 0. 运行纪律（每天先读）

```
目标: 积累高质量判断样本
禁止: 无机会就改系统 / 一次错误就加模块 / 上涨证明模型对 / 下跌证明模型错
原则: 数据 → 判断 → 记录 → 复盘
```

---

## 每日执行表

| 时点 | 任务 | 命令/动作 | 输出 |
|---|---|---|---|
| 05:30 | ① 美股信息扫描 | `python tools/daily_event_collector.py`（+美股检索） | data/events/{date}_events.jsonl |
| 05:45 | ② 跨境产业链雷达 | 美股事件 → A股映射候选（事件→关系→EPS 链） | 候选 Top3-5（仅记录） |
| 15:30 | ③ Growth OS 扫描 | `python tools/run_research_scan.py` | research_pool CSV |
| 15:35 | ④ Research Book | `python tools/build_daily_research_book.py` | research_book md |
| 15:40 | ⑤ 人工判断 3-5 只 | `python tools/decision_cli.py --book ... --resume` | data/ledger/ |
| 23:00 | ⑥ COHR 监控 | 按 prompts/protocols/cohr_monitor_v1.md（先读 configs/cohr.yaml） | output/research/ |
| 随时 | ⑦ Golden Pit 触发 | 持仓跌破触发线 → 执行 Golden Pit Review 模板 | 完整重评 |
| 收工 | ⑧ 5 分钟复盘 | 今天新增/系统发现/人工判断对错 | data/ledger/ |

---

## 每日关注重点

### ① 事件采集后问: 影响哪只票? 影响哪条假设?（E1-E18 分类已自动）

### ③ 扫描后重点看标签冲突:
```
L1 + E0 + Attention A3 → 可能高关注调整, 非忽略 (E v2 视角)
L1 + 探针异常大数字 → 查低基数 (恒瑞教训)
```

### ⑤ 判断记录要点（非买不买）:
```
为什么看/为什么否定 + 依据 + 证伪条件 + 未来验证点
目标: 30天 100 条
```

### ⑥ COHR 每日三问:
```
好公司? (AI需求/1.6T/毛利/FCF)
好价格? (估值/安全边际)
状态变化? (读 trigger_state: 300-335退出三条件)
```

### ⑦ Golden Pit 触发线（configs）:
```
COHR ≤300 已触发(重评完成, 判定"接近")
触发 → 执行模板, 未触发不启动完整分析
```

---

## 新功能冻结纪律

```
发现问题 → 记录到 data/issues/ 或 docs/ISSUE_*.md → T+30 统一处理
禁止运行期改模型/加模块/改协议
```

## T+30 Review（2026-10-02）

```
Growth OS: L/E/P 有效性 | E v2 是否替代 v1 | P 是否转正
XIS:      事件数量 | 哪类有效 | 哪类噪音
Golden Pit: 案例数 | 判断准确率 | 模板 v2
Ledger:   人工判断胜率 | 系统候选转化率 | 错误类型
```

---

## 冻结版本清单（git tag: v35-runtime）

| 组件 | 版本 | 位置 |
|---|---|---|
| Growth OS | v3.5 | growth_os/ + tools/ |
| XIS | v1 | tools/event_scan.py + daily_event_collector.py |
| 04 Alpha | v3 | prompts/protocols/04_alpha_v3.md |
| Golden Pit | v1 | docs/templates/Golden_Pit_Review_Template_v1.md |
| COHR Monitor | v1 | prompts/protocols/cohr_monitor_v1.md + configs/cohr.yaml |
| 边界 | 冻结 | RELATIONSHIP_04_GROWTH_OS.md |
