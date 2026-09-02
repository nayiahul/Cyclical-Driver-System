# Growth OS v3.5 Shadow — 运行期收敛（冻结）

**日期**: 2026-09-02
**状态**: 开发冻结 → 30 天运行期（2026-09-02 ~ 10-02）
**版本角色**: L/E = Production / P = Shadow / Ledger = Production / Calibration = Accumulation

---

## 一、当前系统全景（完整闭环）

```
数据层    PIT 财务/行情（tdx_v20260901_q2）
   ↓
发现层    Discovery（探针）
   ↓
状态层    Lifecycle L（L0-L5）
   ↓
认知层    Expectation E（E0-E3）
   ↓
产业层    Paradigm P（AI_OPTICAL_CYCLE, Shadow only）
   ↓
研究分配  Radar-Quota Allocation
   ↓
投资判断  Memo + Decision Ledger
   ↓
反馈学习  Outcome Ledger + 历史回填 100 条
```

## 二、实证基线（冻结值）

| 能力 | 证据 |
|---|---|
| PIT 治理 | 85% 泄漏归因；披露日治理 |
| L1×E0/E1 | 升级率 53.2-53.9% vs 47.5% 基线（+6pp） |
| L5 | 恢复率 50.2% / 错误率 8.7% / Eff 53% |
| L/E/P 反事实 | 61 次压制光模块 +36.4%（市场 5 倍） |
| P Broken | 毛利转红 = 证伪变量（44% 预警 vs 0% 误杀） |
| 边界 | 行业前瞻归人工（徐工/融捷实证） |

## 三、30 天运行清单（每日 ~10 分钟）

```bash
cd "/Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统"
source .venv/bin/activate

# 1. 全市场研究池（~3 min）
python tools/run_research_scan.py

# 2. 研究书 Top50 + P Shadow 观察区（~1 min）
python tools/build_daily_research_book.py

# 3. 判断留痕 3-5 只（不是 50 只！质量 > 数量）
python tools/decision_cli.py --book output/research_book_{YYYYMMDD}.csv --resume
```

**决策纪律**: 每天 3-5 个高价值判断 → 30 天 ~100 条有效样本

## 四、四个观察指标

| 指标 | 观察内容 | 判定时点 |
|---|---|---|
| 1 A 池命中质量 | DEEP_RESEARCH 标的 30 天后 L/E 状态、Thesis 是否成立 | T+30 |
| 2 人工 Override 价值 | 系统 C vs 人工 A（300308 类）——成功=系统需范式扩展，失败=人类受叙事影响 | T+90 |
| 3 P 层改善研究 | P2 标签是否让 thesis/counter/checkpoints 更清晰（非收益） | T+30 主观+数据 |
| 4 Failure 类型 | 收集 A(系统对)/B(系统错)/C(Override对)/D(Override错) 四类 | 持续 |

## 五、T+30 Review（2026-10-02）决策树

```
检查: 扫描次数 / Decision 数量 / DEEP 比例 / Override 一致性 / P Shadow 价值
    ↓
P 有价值 → v4.0 L/E/P 正式三轴
P 无增益 → L/E 主系统 + P 研究辅助（降级）
新盲区   → 下一轮 Calibration
```

## 六、冻结期间禁止

- ❌ 新增因子/范式插件（机器人/半导体/储能——等模板跑通）
- ❌ 改 L/E Priority 逻辑
- ❌ 大规模开发（边际价值已低于真实反馈数据）
- ✅ 只允许: 每日运行 + 判断记录 + 数据积累

## 七、核心资产（当前全部已推送 GitHub）

- 55 份文档 · ~62 commits · 29 测试
- 7+1 Decision Ledger 样本（五类场景 + 行业排除）
- 100 条历史回填复盘（confirmed 27/partial 53/failed 20）
- 96 只 AI 例外候选池 + 8 只 Shadow 观察
- data/ledger/ 结构化积累中
