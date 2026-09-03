# Runtime Calibration #002 — Human Decision Loop Missing

calibration_id: RUNTIME-CAL-002
type: PROCESS_FAILURE
priority: P0
date: 2026-09-03

## 问题
系统产生大量分析（COHR Review / CAL-001 / MAC-001 / L-relative note），
但未产生"投资者判断数据"——decision_cli 从未真实执行。

实际流程: 数据 → AI分析 → 文档
设计流程: 数据 → AI辅助 → 人工判断 → Ledger → 未来验证

## 影响
30天后若只有 AI 分析档案而无人工判断，系统退化为"研究报告生成器"，
失去"个人投资记忆"的核心价值。

## 修复
- 恢复每日 3-5 条人工 Ledger 记录（必须含反证字段）
- 人工判断 ≥10 条前: 禁止新模块/评分/Gate/Layer
- AI 角色 = 数据提供 + 反证提问, 不替用户下判断

## 反证机制 (Investment Falsification First)
判断流程改为:
  信号 → "最可能骗人在哪里?" → 找反证 → 找支持 → 判断
示例:
  恒瑞: 判断 IGNORE 的反证 = "若Q3创新药收入恢复, 合同负债下降只是确认节奏"
  COHR: 判断等待的反证 = "若1.6T提前爆发且FCF超预期, 当前估值可能低估"
