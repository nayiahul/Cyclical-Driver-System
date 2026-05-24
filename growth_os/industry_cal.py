"""行业翻译器 — 将通用财务指标翻译为行业特定语义。

核心功能：
- 存货增长在半导体/军工是「主动备产」，在服装/零售是「滞销」
- 资本开支在制造/半导体是「扩张信号」，在轻资产行业是「异常」
- 预收款/合同负债在白酒/军工是「订单先行」，在一般行业权重较低
"""
from growth_os.config import (
    INDUSTRY_ADJUSTMENTS, CAPEX_HEAVY_INDUSTRIES, EXCLUDED_INDUSTRIES_L1,
)


def translate_inventory_growth(industry_l3: str, inv_growth_pct: float,
                               revenue_growth_pct: float) -> tuple[bool, str]:
    """翻译存货增长信号。

    Returns:
        (is_red_flag, explanation)
    """
    adj = INDUSTRY_ADJUSTMENTS.get(industry_l3, {})
    threshold = adj.get("inventory_growth_threshold", 1.5)

    if industry_l3 in CAPEX_HEAVY_INDUSTRIES:
        # 半导体/军工等：存货增长可能是主动备产
        if inv_growth_pct <= revenue_growth_pct * threshold:
            return False, f"存货增长{inv_growth_pct:.1f}%在主动备产范围内(阈值{threshold}x营收增速)"
        else:
            return True, f"存货增长{inv_growth_pct:.1f}%超出主动备产合理范围({threshold}x营收增速)"
    elif adj.get("gross_margin_sensitive"):
        # 消费电子等毛利率敏感行业
        if inv_growth_pct > revenue_growth_pct * threshold:
            return True, f"存货增长{inv_growth_pct:.1f}%显著快于营收，警惕渠道积压"
        else:
            return False, ""
    else:
        # 一般行业
        if inv_growth_pct > revenue_growth_pct * 1.5:
            return True, f"存货增长{inv_growth_pct:.1f}% > 营收增速{revenue_growth_pct:.1f}%的1.5倍"
        else:
            return False, ""


def translate_capex(industry_l3: str, capex_growth_pct: float) -> tuple[bool, str]:
    """翻译资本开支信号。"""
    if industry_l3 in CAPEX_HEAVY_INDUSTRIES:
        if capex_growth_pct > 20:
            return True, f"资本开支大增{capex_growth_pct:.1f}%，产能扩张积极（正面）"
        elif capex_growth_pct > 0:
            return True, f"资本开支增长{capex_growth_pct:.1f}%，产能稳步扩张"
        else:
            return False, f"资本开支下降{capex_growth_pct:.1f}%，扩张暂停"
    else:
        if capex_growth_pct > 50:
            return False, f"资本开支异常大增{capex_growth_pct:.1f}%，需关注合理性"
        return False, ""


def get_industry_narrative(industry_l3: str) -> str:
    """获取行业核心叙事。"""
    narratives = {
        "半导体设备": "国产替代+产能扩张周期，看订单(合同负债)和研发转化率",
        "集成电路制造": "资本密集+技术密集，看产能利用率和良率爬坡",
        "白酒": "品牌护城河+预收款先行，看产品结构升级(高端占比)",
        "化学制剂": "管线为王，看研发投入和临床进度",
        "生物制品": "高研发+长周期，看现金跑道和BD能力",
        "医疗设备": "国产替代+出海，看毛利率和海外收入占比",
        "IT服务": "SaaS/订阅转型，看ARR/NDR和获客效率",
        "垂直应用软件": "垂直行业深耕，看续费率和人效",
        "光伏电池组件": "技术迭代+产能竞赛，看技术路线和成本曲线",
        "锂电池": "产能利用率+原材料成本，看上下游一体化程度",
        "航空装备": "订单先行(合同负债)，看交付节奏和型号放量",
        "军工电子": "国产替代+型号驱动，看合同负债趋势",
        "消费电子零部件及组装": "大客户周期+创新驱动，看毛利率和库存周期",
        "品牌消费电子": "品牌溢价+渠道效率，看毛利率趋势和库存健康度",
        "空调": "存量竞争+品牌集中，看现金流和分红",
        "乘用车": "电动化转型+品牌向上，看单车均价和毛利率",
        "汽车电子电气系统": "智能化渗透率提升，看研发和定点项目",
    }
    return narratives.get(industry_l3, f"通用分析框架({industry_l3})")
