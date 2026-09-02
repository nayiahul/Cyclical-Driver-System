# 04_事件型黄金坑｜短中期 Alpha 猎手 v3（研究协议 · 校对入库版）

> 入库日期: 2026-09-03 | 来源: 用户 SOP
> 校对原则: A 投资原则(长期不变) + B 执行流程(系统规则) 入库；
> C 仓位状态 → configs/；涉及"当前持仓/成本/时点"的均移出，引用 configs。

## 核心目标

在美股/A股/港股，用公开合法可核验信息寻找 1交易日~6个月 的：
事件错杀/盈利上修/特殊事件/产业链滞后/基本面拐点/强势突破/资金催化。

**禁止**：未核实传闻、纯技术形态、纯价格异动、热点题材、"美股涨A股没涨" 单独作交易理由。

## 固定执行时点（北京时间）

- 05:30 美股收盘后：美股/全球科技/AI链/创新药/海外→A/H映射 → E事件→EIS→G0/G1-G7→Forward EPS→OQS→MRS→Leadership→ERS/TQS
- 15:30 A股收盘后：完整复盘 + G0/G1-G7候选池更新
- 20:30 晚间公告主扫描：战略入股/5%持股/大额订单/认证/Design Win/Buyback/业绩预告/指引变化
- 22:30 补漏 + 次日观察计划
- 通知规则：仅 S级/A级/特别强B级/重大证伪 通知；普通波动沉默

## 完整链路（任何一层不过关，不因"故事好"强行升级）

E层事件发现 → EIS → G0/G1-G7 → Forward EPS Test → Earnings Acceleration → Price-in → False Lag → OQS → MRS → Leadership/RS → Entry Structure → ERS → TQS → Risk/Reward → Risk Unit → STOP-FUNDAMENTAL + STOP-PRICE → 加仓/减仓规则 → 最终动作

## E1-E18 事件雷达（与 XIS event_scan 共用词库——见 tools/event_scan.py）

E1财报异常 / E2指引变化 / E3盈利修正 / E4大客户 / E5订单 / E6产品 / E7价格 / E8产能 /
E9供应链 / E10竞争 / E11战略资本 / E12公司行动 / E13 M&A / E14管理层内部人 / E15政策监管 /
E16法律治理 / E17被动资金 / E18宏观冲击

纪律: E15/E18 必须穿透 政策→客户→订单→Revenue→Margin→EPS；禁止只写宏观故事。

## Negative Event Radar

CEO/CFO离职、客户丢失、砍单、Guidance Cut、毛利下降、诉讼、做空、关税、出口限制、停产、减值等。
全部执行 **Price Damage vs Fundamental Damage** 量化。
Price >> Fundamental 且护城河未坏/资产负债表健康/长期逻辑未坏 → G1 候选；否则排除。

## EIS / G0 / G1-G7 / OQS / MRS / ERS / TQS / Risk Unit / 止损 / R/R

(详见用户原始 SOP 第五节~二十三节——数值阈值为可执行规则，全部保留)

关键固定阈值：
- EIS: <50噪音 / 50-69普通 / 70-84重要 / ≥85深挖（高≠可买）
- G0提前仓: G0≥A + OQS≥82 + ERS≥80 + TQS≥80 + R/R≥2 + Catalyst≤20交易日 + STOP明确；仓位上限定10-15%计划仓
- OQS: S90-100 / A85-89 / B75-84 / C60-74 / D<60
- MRS: ≥70 Risk-On / 45-69 Neutral / <45 Risk-Off（不改OQS，改ERS/TQS/仓位）
- ERS: OQS≥85但ERS<75 → 好机会坏买点，等待
- TQS: ≥85高质量 / 80-84小仓 / 70-79等待 / <70禁止（即使OQS=95）
- Price-in封顶: 20日同逻辑涨>20%重复确认→79；60日涨>40%无新EPS修订→84
- Risk Unit: 单笔账户风险 0.5%-1%；仓位由风险预算决定，不由"看好"决定
- R/R: 普通≥1.5；G0提前≥2
- 双止损: STOP-FUNDAMENTAL(大订单取消/EPS下修/客户流失/护城河下降) + STOP-PRICE(跌破Pivot/支撑/异常放量) 任一触发即重评；中短期不得因"长期逻辑没坏"无限容忍

## 陷阱识别（每次必查）

Value/Growth/Catalyst Trap、False Lag、Fake Turnaround、Momentum/Rumor/Falling Knife Trap、Crowded Trade、Sell-the-News。
无法回答"市场现在为什么错"→ 不得高评级。

## 固定输出格式

总览表: 股票|E事件|EIS|G阶段|Primary|Secondary|OQS|MRS|Leadership|EA|ERS|TQS|Forward EPS|R/R|动作
重点候选 26 问（Why now/新信息等级/Forward四表/EA/Price-in/False Lag/MRS/Leadership/Entry/R/R/Risk Unit/双STOP/加仓/三反证/最终动作）。
最终动作限: 提前研究/提前小仓/立即研究/等待买点/小仓试错/进A级候选/进B级观察/继续观察/排除。
每轮最多 3 个真正值得投入的机会；无则明写"今天没有值得出手的机会"。

## 04-10 复盘系统

T+1/3/5/10 + MFE/MAE + EPS兑现 + Forward EPS Revision + G0提前天数 + EIS/OQS/MRS/Leadership/EA/Entry/ERS/TQS/初始R/R/实际Entry/STOP/止损触发/加仓/最终收益。
每 20 样本统计: G1-G7胜率/盈亏比/MAE/MFE + TQS分档 + Risk-On/Neutral/Off + Leader/Improving/Neutral/Laggard + Entry类型表现。
**样本不足禁止声称"稳定胜率"。**

## 交易铁律（十六条）

好公司≠好股票≠好价格≠好买点；好事件≠Forward EPS变；EPS变≠市场未定价；未定价≠现在买；
OQS高≠TQS高；跌多≠黄金坑；没涨≠滞后；Beat≠加速；突破≠基本面成立；
Risk-Off降执行风险不降研究质量；G1只在损伤不扩大时加仓；G2/G5/G6只向赢家加仓；
买入前必须知道: 为什么买/错在哪/错了亏多少/何时走/何时加；
小账户第一是避免大亏，等待真正高质量不对称机会。

## 核心公式

Alpha Quality = New Info × Expectation Gap × Forward EPS Impact × Catalyst Reliability ÷ Permanent Damage Risk
G1: Price Damage > Fundamental Damage
G2: Fundamental Improvement > Price Reaction
G4: EPS Transmission > Market Recognition
G3: Value Unlock > Valuation Recognition
G5: Business Improvement > Investor Belief Change
可执行 = High OQS + 可接受估值 + Good MRS + Leadership + Good Entry + High ERS/TQS + Clear Stop + 诱人 R/R

## 本协议与 Growth OS 边界

- 本协议=行动层(交易窗口/风险管理)，Growth OS=认知层(研究池/Thesis)
- 候选来源: Growth OS 研究池接口（Core/Watchlist/Shadow）
- 复盘数据回传 Growth OS Ledger（"判断对但交易败"归因）
- 不自动执行任何交易动作
