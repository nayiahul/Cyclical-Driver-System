# Industry Paradigm Map v1 — 行业范式状态机映射

**日期**: 2026-09-01
**依据**: Industry Adaptive State Machine Audit（12,267 行, 2022-2023 采样）
**用途**: Investment State Model v2 的行业参数化基础

---

## 一、范式定义与最佳状态（实证）

| 范式 | 行业 | L1-L0 增量 | 最佳状态 | 含义 |
|---|---|---|---|---|
| **cycle_manufacturing** | 有色/机械/化工/钢铁/建材/煤炭 | **+5.5pp** | **L1 早期** | 预期差在变化发生、市场未确认时最大 |
| **tech_growth** | 电子/通信/计算机/军工/传媒 | -1.6pp | L0（状态机不适用） | 探针信号与收益无关；定价由技术/主题驱动 |
| **consumer** | 医药/食品/家电/纺织/农业 | +2.8pp | L1（弱） | 早期有效但幅度小 |
| **defensive** | 银行/公用/交运/非银 | +1.3pp | **L2 确认** | 低波动行业需确认后才值得研究 |

## 二、行业 → 范式映射（SW1 级）

```python
PARADIGM_MAP = {
    # 周期制造: L1 优先 (核心研究区)
    "有色金属": "cycle_manufacturing", "基础化工": "cycle_manufacturing",
    "机械设备": "cycle_manufacturing", "钢铁": "cycle_manufacturing",
    "煤炭": "cycle_manufacturing", "石油石化": "cycle_manufacturing",
    "建筑材料": "cycle_manufacturing",
    # 科技成长: 状态机不适用 (需不同 Discovery 信号)
    "电子": "tech_growth", "通信": "tech_growth", "计算机": "tech_growth",
    "传媒": "tech_growth", "国防军工": "tech_growth",
    # 消费: L1 弱有效
    "食品饮料": "consumer", "医药生物": "consumer", "家用电器": "consumer",
    "纺织服饰": "consumer", "商贸零售": "consumer", "农林牧渔": "consumer",
    "社会服务": "consumer", "美容护理": "consumer",
    # 防御: L2 确认优先
    "银行": "defensive", "非银金融": "defensive", "公用事业": "defensive",
    "交通运输": "defensive", "房地产": "defensive",
}
```

## 三、状态机 v2 规则（行业参数化）

```python
def classify_with_paradigm(code, disc, rps, paradigm):
    if paradigm == "tech_growth":
        return "L0", "IGNORE"   # 探针状态机不适用 → 不进入此通道
    if paradigm == "defensive":
        # 防御行业: 确认后优先 (L2)
        if disc >= 0.5 and rps >= 40: return "L2", "B"
        return "L0", "IGNORE"
    # cycle_manufacturing / consumer: L1 优先 (原逻辑)
    if disc >= 0.5:
        if rps < 40:  return "L1", "A"
        if rps < 70:  return "L2", "B"
        return "L3", "C"
    return "L0", "IGNORE"
```

## 四、重要限制

1. 样本窗口 2022-2023（熊市+震荡）——科技行业"L0 最佳"可能受熊市影响，需 2024-2025 牛市验证
2. 通信 L0 +21.1% 是异常值（可能少数暴涨股驱动），需检查样本构成
3. 煤炭/石油样本量小（n<100），结论弱
4. tech_growth 需要**不同的 Discovery 信号**（技术突破/订单/渗透率），而非 CAPEX/毛利探针

## 五、下一步

1. State Machine v2 编码（本映射入 `growth_os/state_machine.py`）
2. 扩展采样到 2024-2025 验证范式稳定性
3. tech_growth 范式单独设计 Discovery 信号（Phase 3）
4. 决定状态机接入 run_screen 输出（研究优先级标签）
