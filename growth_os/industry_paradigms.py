"""行业范式引擎 — 不同行业走不同的评估框架。

6 个范式组覆盖 Top 20 中出现的核心行业，其余回退到通用框架。

每个范式定义：
  - 核心探针树（哪些探针最相关，哪些不适用）
  - 默认估值框架
  - 增长驱动力
  - 行业特有风险
"""
from __future__ import annotations
from typing import Optional


# ═══════════════════════════════════════════════
# 范式定义
# ═══════════════════════════════════════════════

INDUSTRY_PARADIGMS = {
    # ── 硬科技制造 ──
    "hardware_tech": {
        "name": "硬科技制造",
        "industries": {
            "半导体设备", "半导体材料", "集成电路制造", "集成电路封测",
            "数字芯片设计", "模拟芯片设计", "通信网络设备及器件",
            "通信终端及配件", "军工电子", "航空装备", "航天装备",
            "光学元件", "被动元件", "印制电路板", "电子化学品",
        },
        "primary_probes": ["CAPEX效率", "订单领先性", "客户集中度"],
        "skip_probes": [],
        "valuation_framework": "PEG（技术扩散型，成长股框架完全适用）",
        "growth_driver": "CAPEX扩张 + 技术迭代 + 国产替代",
        "key_risks": ["技术路线切换", "客户集中度高", "CAPEX周期顶部冲动"],
        "narrative_template": "技术迭代驱动成长，关注CAPEX效率和客户结构",
    },
    # ── 软件/SaaS ──
    "software_saas": {
        "name": "软件/SaaS",
        "industries": {
            "横向通用软件", "垂直应用软件", "IT服务",
        },
        "primary_probes": ["订单领先性", "毛利率韧性", "CAPEX效率"],
        "skip_probes": [],
        "valuation_framework": "PEG（高增长）/ PE分位（成熟期）",
        "growth_driver": "合同负债 + 续费率 + 人效",
        "key_risks": ["订阅增速放缓", "客户流失", "估值溢价压缩"],
        "narrative_template": "订阅/续费驱动成长，关注合同负债先行性和人效",
    },
    # ── 医疗创新 ──
    "medical_innovation": {
        "name": "医疗创新",
        "industries": {
            "化学制剂", "其他生物制品", "医疗耗材", "医疗设备",
            "体外诊断", "医药流通", "中药",
        },
        "primary_probes": ["毛利率韧性", "客户集中度", "订单领先性"],
        "skip_probes": [],
        "valuation_framework": "PEG（管线驱动型，需关注研发转化率）",
        "growth_driver": "研发管线 + 审批周期 + 集采格局",
        "key_risks": ["集采降价", "研发失败", "审批延迟"],
        "narrative_template": "研发管线驱动成长，关注毛利率韧性和集采格局演变",
    },
    # ── 消费品牌 ──
    "consumer_brand": {
        "name": "消费品牌",
        "industries": {
            "白酒", "啤酒", "其他酒类", "乳制品", "调味发酵品",
            "品牌消费电子", "游戏", "非运动服装", "多业态零售",
        },
        "primary_probes": ["毛利率韧性", "订单领先性", "客户集中度"],
        "skip_probes": [],
        "valuation_framework": "PE分位（品牌溢价型，稳定增长）",
        "growth_driver": "品牌溢价 + 渠道扩张 + 产品升级",
        "key_risks": ["消费降级", "渠道变革", "品牌老化"],
        "narrative_template": "品牌溢价驱动成长，关注毛利率趋势和渠道效率",
    },
    # ── 工业制造 ──
    "industrial_manufacturing": {
        "name": "工业制造",
        "industries": {
            "底盘与发动机系统", "其他汽车零部件", "汽车电子电气系统",
            "工控设备", "其他专用设备", "其他通用设备",
            "逆变器", "其他电源设备", "风电整机", "光伏电池组件",
            "光伏辅材", "锂电池", "电池化学品", "线缆部件及其他",
            "金属制品", "其他化学制品", "其他化学原料", "膜材料",
            "消费电子零部件及组装",
        },
        "primary_probes": ["CAPEX效率", "订单领先性", "毛利率韧性"],
        "skip_probes": [],
        "valuation_framework": "PEG（caution，周期属性强，需结合CAPEX周期判断）",
        "growth_driver": "CAPEX周期 + PMI + 产能利用率",
        "key_risks": ["产能过剩", "原材料价格", "下游需求周期性波动"],
        "narrative_template": "工业周期驱动成长，关注CAPEX周期位置和订单可见度",
    },
    # ── 通用框架（回退） ──
    "generic": {
        "name": "通用框架",
        "industries": set(),  # 匹配所有未覆盖行业
        "primary_probes": ["订单领先性", "CAPEX效率", "毛利率韧性", "客户集中度"],
        "skip_probes": [],
        "valuation_framework": "由Regime路由决定",
        "growth_driver": "通用财务分析",
        "key_risks": ["通用风险"],
        "narrative_template": "通用分析框架，建议人工复核行业特征",
    },
}

# 构建行业→范式快速查找表
_INDUSTRY_MAP: dict[str, str] = {}
for paradigm_key, paradigm in INDUSTRY_PARADIGMS.items():
    if paradigm_key == "generic":
        continue
    for industry in paradigm["industries"]:
        _INDUSTRY_MAP[industry] = paradigm_key


def get_industry_paradigm(industry_l3: str) -> dict:
    """根据申万三级行业名返回评估范式。

    Args:
        industry_l3: 申万三级行业名称

    Returns:
        paradigm dict，包含 name/primary_probes/skip_probes/valuation_framework/
        growth_driver/key_risks/narrative_template
    """
    key = _INDUSTRY_MAP.get(industry_l3)
    if key:
        return dict(INDUSTRY_PARADIGMS[key])
    return dict(INDUSTRY_PARADIGMS["generic"])


def list_paradigms() -> list[dict]:
    """列出所有已定义的范式（不含通用框架）。"""
    return [
        {"key": k, "name": v["name"], "industries_count": len(v["industries"])}
        for k, v in INDUSTRY_PARADIGMS.items()
        if k != "generic"
    ]
