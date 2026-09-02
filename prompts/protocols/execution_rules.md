# Execution Rules — 研究协议通用执行纪律

> 所有 prompts/protocols/* 下协议的通用执行规则。协议冲突时以此为准并显式标注。

## 1. 核验先行（防漂移）

- 报告中的价格/财报/事件数字，输出前必须实时核验（AnySearch/akshare/官方源）
- 核验状态标注: ✅已核验 / ⚠️未证实 / ❌与事实不符
- 引用的每条"硬数据"必须有来源；无来源的定性判断需显式说明

## 2. 状态与协议分离

- 协议(prompts/)只含投资原则与流程；仓位/成本/触发状态在 configs/*.yaml
- 每次执行前**先读 configs**，Decision Gate 必须对照触发线
- SOP 与当前状态冲突时（如现价已触发重评线但报告写"等待"）→ 冲突必须浮出水面并执行 Gate 要求

## 3. 输出规范

- 输出文件: output/research/{protocol}_{date}.md
- 必带: 数据日期 / 核验状态 / 信息来源 / Decision Gate 结果
- 结论动作限协议允许集合；无机会明写"今天没有值得出手的机会"

## 4. 系统边界

- 产出 = 建议 + 数据包；交易动作由用户执行
- 事件/新闻不自动改 Growth OS 的 L/E/P；04 评分不回流研究层
- 重大判断与触发线状态 → data/ledger/（T+30 可复盘）

## 5. 数据积累

- 事件: data/events/{date}_events.jsonl
- Thesis: data/thesis/{code}.json
- 报告: output/research/
- 30 天积累后统一复盘，不在运行中改协议
