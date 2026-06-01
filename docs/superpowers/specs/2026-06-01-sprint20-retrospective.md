# Sprint 20 回顾：归因系统从坍缩到恢复

> 记录 2026-06-01 与 ChatGPT / DeepSeek / Kimi / Yuanbao 多轮对话的核心结论、采纳意见及后续推进方向。

---

## 一、Sprint 19 → 20 演化路径

### Sprint 19（已完成）
- L1 排雷 → 仓位传导：L1 review 标的从核心降级到标配
- 周期状态范式感知：tech_penetration/brand_premium 不再误判为周期顶部
- **结论：评分/仓位体系已稳定，可进入静默实盘**

### Sprint 20（已完成）
- **根因**：classifier.py:103 `GM↑ + RD>3% + ROIC>10% → tech_penetration` 捕获了四种不同增长机制（光模块/游戏/医药/军工），归因熵 1.595 bits
- **修复**：行业模板化（industry_template.py）+ Sub-Gene 解释层
- **效果**：归因熵 1.595 → 2.75 bits，新易盛 price_cycle→tech_penetration，郑中设计 share_gain→project_cycle

### Sprint 20.1（已完成）
- P0-3：drug_ramp 加入 STRUCTURAL_SOURCES（三生国健周期状态修正）
- P0-1/2 部分修复：_GENE_CORRECTIONS 出口一致性校正 + 摘除 platform_network enable

### Sprint 20.2（已完成）
- 游戏 rd_threshold 参数化（3.0%，通过 industry_template 配置）
- 删除 SUB_GENE_MAP 中 `share_gain+垂直应用软件→platform_network` 错误映射
- sub_gene 语义冲突防御层（_SUB_GENE_CONFLICTS）
- _GENE_CORRECTIONS 条件化（仅 enable 基因全部 miss 时触发）
- **效果**：恺英 hit_game、合合 sub_gene 置空、quality_growth 15%

---

## 二、方法论转变（核心收获）

### 旧模式：规则工程
```
发现 bug → 加一条 if-then → 引发新交互 → 再加一条 if-then
```

### 新模式：规则引擎 + 防御层
```
规则引擎（粗筛，允许误匹配）
    ↓
防御层（精修，纠正已知矛盾模式）

复杂度：O(n+m) 而非 O(n×m)
```

### 关键原则
1. **不改已有规则阈值**（避免连锁反应）
2. **出口一致性校正**替代调参（_GENE_CORRECTIONS 映射表）
3. **摘除错误映射**替代加更多准入条件（删 1 行 > 加 3 行）
4. **参数化配置**替代硬编码（rd_threshold 通过 industry_template 读取）

---

## 三、架构洞察

### 规则引擎的复杂度临界点
- classifier.py 20+ 条规则按优先级排列，新增一条可能覆盖已有四条
- 隐式交互：规则 A 的 early return 阻止规则 B；规则 C 的置信度覆盖规则 D
- 每加一个新 Gene，需手动更新 persistence_map + risk_map + cycle_state 保护列表 → 遗漏是必然的

### 架构双轨
- Composite→仓位（旧） vs Gene→仓位（新）两套逻辑并存
- 郑中设计 Composite 77.4 vs project_cycle 轻仓 是典型案例
- Sprint 20.1 加了冲突标记（⚠️ 双轨冲突），但未统一

### sub_gene_map 是最脆弱环节
- 纯查表 `(gene, industry)→label`，无准入条件，无验证
- Gene 错则 sub_gene 跟着错
- Sprint 21 方向：sub_gene eligibility 机制（从查表升级为条件判定）

---

## 四、Sprint 21 候选方向（按优先级）

### P0：标注集建设
- 当前 5 例（annotations/sprint20_eval.yaml）
- 目标 30+ 例，覆盖游戏/光模块/医药/军工/装修 5 个行业各 5-10 例
- 每次 classifier 变更后跑回归测试，自动检测归因退化
- **这是从"规则工程"升级到"规则工程+测试工程"的分水岭**

### P1：sub_gene eligibility 机制
- 当前：`(gene, industry) → label` 纯查表
- 目标：`sub_gene = f(gene, industry, metrics)` 带条件判定
- 替换临时方案 _SUB_GENE_CONFLICTS

### P1：quality_growth 拆分
- 当前 quality_growth 正在变成"垃圾桶"（15% 占比）
- 拆为 quality_growth（已知驱动但证据不足） + unknown_growth（驱动未识别）
- ChatGPT 建议：显式化 unknown 比伪装成 quality_growth 更诚实

### P2：Gene→仓位架构决策
- 当前两套逻辑并存
- 触发条件：标注集 ≥ 30 例 + Gene persistence 校准完成
- 选项 A：正式接受 Gene→仓位，Composite 降级为参考分
- 选项 B：统一回评分驱动（不推荐）

### P2：混合归因
- 新易盛 case：70% tech_penetration + 30% price_cycle
- 当前用光模块豁免替代
- 等 sub_gene 稳定、标注集充足后再引入概率框架

---

## 五、Telemetry 体系

### Layer 1（已实现）
- 每次 run_screen 输出 `output/telemetry/{date}.json`
- 记录：entropy, gene_distribution, quality_growth_ratio, warnings

### Layer 2（2 周后）
- Gene Turnover：跨期归因变化率
- 报警阈值：Turnover > 30%

### Layer 3（4 周后）
- Conflict Rate：Composite 高分但 Gene 低持续性的标的占比
- 报警阈值：Conflict Rate > 20%

### 监控指标优先级
1. Gene Entropy（归因多样性）
2. Quality Growth Ratio（垃圾桶膨胀检测，阈值 30%）
3. Gene Turnover（归因稳定性）
4. Conflict Rate（双轨矛盾程度）

---

## 六、已采纳的关键意见

| 来源 | 意见 | 状态 |
|------|------|------|
| ChatGPT | 行业模板化 P0 | ✅ Sprint 20 |
| ChatGPT | sub_gene 只读解释层 | ✅ Sprint 20 |
| ChatGPT | 不调阈值，做出口一致性校正 | ✅ Sprint 20.1 |
| ChatGPT | 摘除错误映射而非加更多条件 | ✅ Sprint 20.1/20.2 |
| ChatGPT | Telemetry > Matrix（先做观测后做展示） | ✅ Sprint 20 |
| DeepSeek | 参数化 rd_threshold | ✅ Sprint 20.2 |
| Kimi | _GENE_CORRECTIONS 条件化 | ✅ Sprint 20.2 |
| Kimi | 标注集不能完全搁置 | ✅ Sprint 20.1 eval.yaml |
| Yuanbao | 宁可解释少，不能解释假 | ✅ sub_gene 防御层 |
| Yuanbao | 出口一致性校正而非调阈值 | ✅ Sprint 20.1 |

## 七、搁置但记录的意见

| 来源 | 意见 | 搁置原因 |
|------|------|----------|
| ChatGPT | sub_gene eligibility 机制 | 需要重构 assign_sub_gene，Sprint 21 |
| ChatGPT | quality_growth 拆为两个基因 | 需要新增 unknown_growth + 全套映射 |
| ChatGPT | Gene-Regime Matrix 可视化 | 等 4 周 Telemetry 数据积累后决定画什么 |
| DeepSeek | 正式接受 Gene→仓位架构 | 需要 30+ 标注样本后决策 |
| 全部模型 | 混合归因 | 标注集不足，概率框架风险高 |

---

## 八、当前系统状态

- **评分层**：L1-L5 → Composite（稳定，Sprint 19 封版）
- **仓位层**：Composite + persistence + L1 review → position（稳定）
- **归因层**：classifier → gene + sub_gene（Sprint 20.2 完成，熵 2.75 bits）
- **监控层**：Telemetry Layer 1 JSON 存档（已实现）
- **评估层**：5 例标注（已创建，待扩充）
- **静默实盘期**：已启动，每日 Top 20 + 每周五复盘
