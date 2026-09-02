# COHR 每日消息检查 · 研究协议 v1（校对入库版）

> 入库日期: 2026-09-03 | 来源: 用户 SOP
> 校对: 投资框架(长期不变)入库；当前持仓/成本/触发线 → configs/cohr.yaml（决策前必读）
> 执行时点: 北京时间每天 23:00

## 投资框架（固定优先级）

1. 商业模式 2. 护城河 3. 财务质量 4. OCF/FCF 5. 估值 6. 风险
巴菲特/芒格框架；3-10年研究周期 + 6-12月阶段机会；不追涨；不因股价涨跌改内在价值；
寻找黄金坑（错杀/行业恐慌/财报后过度下跌）。**先读 configs/cohr.yaml 的状态与触发线。**

## 检查层次

### L1 公司自身（官方优先）
IR 公告/Earnings/Presentation/产品/合作/产能/并购/管理层变化 + SEC(10-K/10-Q/8-K/Form4/144/13D/13G/Proxy)
Form4 纪律: 区分公开市场买卖 / 10b5-1 / RSU归属 / 税款代扣 / 期权行权——RSU代扣≠主动减持，未确认不作负面。

### L2 商业模式与护城河
赚钱结构(Datacenter/Industrial/激光/InP/EML/VCSEL/CW/Transceiver/CPO)；AI占比↑趋势；护城河 10 项(技术/InP/垂直整合/认证/Hyperscaler关系/规模/供应链/良率/成本)——变化标 ↑/→/↓

### L3 AI光通信产业链
- Hyperscaler CapEx（NVIDIA/Google/MSFT/Meta/AMZN/Oracle/CoreWeave/xAI）——**区分已发生 CapEx 与未来计划**
- 技术路线: 400G→800G→1.6T→3.2T/200G-lane/400G-lane/EML/CW/SiPh/CPO/NPO/OCS/LPO/AC/Optical I/O——回答"升级逻辑是否继续成立"
- NVIDIA 合作: 是否从战略背书转化为真实收入/现金流

### L4 竞争对手
LITE/FN/AVGO/MRVL(+AAOI/旭创/新易盛/Cisco/Arista/Corning/MACOM)
竞对财报 Read-through: Revenue/GM/OM/EPS/CapEx/Inventory/OCF/FCF/1.6T/CPO/Guidance
**关键问题: 行业很好但 COHR 是否跑输?（不得简单归因行业周期）**

### L5 财务质量（财报/重大更新时跟踪）
Revenue/YoY/Datacenter收入/GM/OM/GAAP&Non-GAAP EPS/OCF/FCF/CapEx/Inventory/AR/Debt/Cash/Net Debt/摊薄股数/SBC/Goodwill/Intangibles/ROIC/Incremental ROIC

### L6 现金流（最高优先级）
FCF = OCF - CapEx
危险信号: Revenue/EPS↑ 但 Inventory↑↑ + CapEx↑↑ + OCF↓ + FCF长期为负 → 提高风险
CapEx回报链: 新增CapEx→新增Revenue→新增OP→新增FCF→Incremental ROIC

### L7 宏观（每日检查不过度解读）
Fed/2Y/10Y(估值关键)/CPI/PCE/非农/DXY(二级)/WTI(噪音除非暴涨)/VIX(恐慌分级)/Nasdaq/SOX
**SOX 对照法**: COHR跌+SOX跌→行业因素; COHR跌+SOX涨→查公司特有风险

### L8 贸易/地缘（双向分析）
美限中国光模块(可能COHR份额↑ 但 中国限InP/材料 可能扩产成本↑)——不能只写利好

## 信息分类

A 直接影响(Revenue/Orders/GM/Capacity/Share/FCF) / B 间接影响(DCF/PE/风险偏好/融资成本) / C 噪音(单日波动/社媒传言/单分析师目标价/Nasdaq±0.5%/油价1%)

## 每日 20 问

商业模式变没变/护城河↑→↓/AI逻辑/800G-1.6T-CPO/份额/Revenue/GM/OCF/FCF/Inventory/CapEx回报/ROIC/资产负债表/竞对抢份额/管理层兑现/SEC新风险/估值(极贵~极端低估)/安全边际/下跌归类(基本面恶化·行业周期·宏观压缩·恐慌·波动·真错杀)/是否达黄金坑标准

## 黄金坑十条件（缺一不可）

1股价明显跌 2情绪悲观 3基本面无永久恶化 4AI长期需求成立 5护城河未降
6现金流问题可解释有修复路径 7资产负债表安全 8估值明显安全边际 9清晰修复催化 10证伪风险可控
**禁止"跌很多=黄金坑"。**

## 估值纪律

不机械每日重算 DCF；仅在触发时重估(财报/指引/长期预期/GM假设/FCF Margin/WACC/股价大幅变/新合作/格局变化)。
固定看: PE/Forward PE/EV-EBITDA/EV-Sales/FCF Yield/DCF/Reverse DCF
回答: "当前股价需要未来多少年增长才合理"

## 每日输出模板（详见用户原始 SOP 第二十节 10 段结构）

开头固定: # COHR 每日消息检查｜日期
总判断表(14模块+较昨日) → 今日最重要1-3条 → 公司自身 → AI产业链 → 竞对 → 宏观表 → A/B/C分类 → 估值与安全边际 → 现有仓位操作 → 新资金操作
**报告最前必须放 Decision Gate（见下）**

## Decision Gate（2026-09-03 加入——状态变量进决策前检查）

```
=====================
执行状态检查 (读 configs/cohr.yaml)
=====================
当前价格: <实时核验>
关键触发线: <yaml 中的 review_line 等>
状态: <未触发/已触发/观察区>
要求: <触发则必须完整重评; 未触发按协议例行检查>
禁止: <触发状态下继续默认等待>
```

## 最终评级与动作

基本面/护城河/AI逻辑/财务质量/OCF-FCF/CapEx回报/宏观/估值/安全边际 各 ★
现有仓位: 加仓/持有/等待/择机减仓/减仓/退出
新资金: 不买/观察/小仓试仓/分批买入/重点买入
黄金坑: 未出现/接近/已出现/排除

## 分析纪律

每天区分: 企业变了没有 / 价格变了多少 / 赔率有没有改善
无实质变化必须明写: "今日没有足以改变长期投资逻辑/估值区间/操作策略的新信息"
核心问题: COHR 是"好公司+好价格"还是只有"好公司"?
