# Growth OS Runtime Protocol v1.0 — 运行期守护协议

**生效日期**: 2026-09-02 | **冻结期**: 30 天（至 2026-10-02 T+30 Review）
**目的**: 积累真实判断数据，而非快速优化模型。防止"见一个异常改一次模型"污染迭代纪律。

---

## Rule 1：Issue 处理纪律

发现异常（标签不符常识 / 结果与判断冲突 / 数据字段异常）时：

```
发现问题 → 记录 Issue → 保存案例 → 进入 Calibration Queue → T+30 统一评估
```

**禁止**: 发现一个案例立即修改规则（L5 指标错误、E 层误分类教训：先量化再修）。

## Rule 2：标签冲突处理

当"系统判断 ≠ 人工认知"：

```
Step 1 数据核验: 财务/时间点/字段定义/是否低基数（如恒瑞 +371% 实为低基数）
Step 2 分类: A 公司问题 / B 市场状态问题 / C 指标问题 / D 人工行业判断
Step 3 Ledger 记录（不立即修复）
```

## Rule 3：新功能冻结

运行期禁止新增：新因子 / 新评分 / 新行业模型 / 新自动决策规则。
所有想法进入 Wishlist，T+30 Review 统一评估。

## Rule 4：人工职责边界

| 系统负责 | 人工负责 |
|---|---|
| 5000→50 筛选、状态识别、研究排序、证据整理 | 产业趋势、竞争格局、政策变化、周期判断 |

## Rule 5：Ledger 优先（每日）

每天 3-5 条高质量判断（非 50 只），每条含：
Decision + Reason + Counter Thesis + Validation Point

## Rule 6：Shadow 不决策

E v2 / P_AI_OPTICAL 只展示提醒（Memo Warning 行），不改变 L/E Production 优先级。
30 天后用 Ledger 数据比较 v1 vs v2 谁更符合人工判断。

## 已知 Issue 队列（T+30 统一评估）

| Issue | 案例 | 层级 | 修复候选 |
|---|---|---|---|
| E-State Misclassification | 300308（高关注回调误标忽略） | E 层 | E v2 三维（Attention/Expectation/Price） |
| Probe Low Base Bias | 600276（合同负债+371% 低基数） | Discovery 层 | 绝对规模/环比确认/利润质量三门槛 |

## 每日流程

```bash
python tools/run_research_scan.py           # ① 扫描 (~2min)
python tools/build_daily_research_book.py   # ② Book (~1min, 含双标签+Warning)
python tools/decision_cli.py --book ... --resume  # ③ 3-5 只判断
```

## T+30 Review 检查项（2026-10-02）

1. 扫描次数 / Decision 数量（目标 ≥100） / DEEP 比例
2. E v1 vs E v2 人工一致性（Ledger 中人工判断与哪版标签更吻合）
3. P Shadow 价值（8 只观察标的的研究行为）
4. Issue 队列验证（E v2 是否替换 v1 / Probe 门槛设计）
5. 决策: v4.0 三轴是否启动

## Rule 7：事件扫描（研究层必做 — FCC 教训 2026-09-02）

**背景**: 中际旭创案例 — FCC 禁令(8/4)是最大下跌驱动, 但 akshare 个股新闻不覆盖
外媒政策事件, 系统财务数据更无法发现。政策/制裁类事件 = 第一级风险变量。

**规则**: 任何 DEEP_RESEARCH 标的研究前必须执行:
```bash
python tools/event_scan.py --code XXXXXX --name 名称 --keywords "行业关键词,政策关键词"
```
双源: ① akshare 公告+个股新闻 (公司事件) ② AnySearch Web (政策/行业外媒事件)

**风险响应**: 扫描结果含 ⚠️ 高风险(政策/制裁/立案)时:
1. 事件记入 Ledger counter_thesis / check_points
2. 研究结论必须显式评估该事件影响 (不能只依赖财务)
3. 重大政策事件(如 FCC 禁令) = 人工研究优先项 (Rule 4 边界)

**设计原则**: 事件信息 = 研究层输入, 不进入自动评分 (防噪声, 与 RPI 教训一致)
