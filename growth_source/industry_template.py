"""行业模板配置 — Sprint 20: 控制不同行业的基因判定规则。

设计原则: 行业特例全部参数化在此文件,classifier 只读配置、不写特例。
"""
from __future__ import annotations

# ── 已知光模块标的（用于 L3+名称双重判定，无 business_desc 时的补充） ──
OPTICAL_CODES = {"300308", "300502", "688127", "300394", "300570", "688313"}

OPTICAL_NAME_KEYWORDS = ["光模块", "光通信", "光器件", "光芯片", "800G", "1.6T", "光互联"]

INDUSTRY_RULES: dict[str, dict] = {
    # ── 游戏：高研发是内容制作，非技术渗透 ──
    "游戏": {
        "disable": ["tech_penetration"],
        "enable": ["product_cycle", "hit_game"],
        "rd_threshold": 3.0,  # Sprint 20.2: 内容型游戏公司 rd=3-5% 仍是显著内容投入
        "fallback_gene": "quality_growth",
        "sub_gene": "product_cycle",
    },

    # ── 装修装饰/商业物业：不存在典型份额战争 ──
    "装修装饰": {
        "disable": ["share_gain"],
        "enable": ["project_cycle", "real_estate_recovery"],
        "fallback_gene": "quality_growth",
        "sub_gene": "project_cycle",
    },
    "商业物业经营": {
        "disable": ["share_gain"],
        "fallback_gene": "quality_growth",
        "sub_gene": "rental_growth",
    },

    # ── 医药生物：创新药放量/国产替代 ──
    "其他生物制品": {"enable": ["drug_ramp"]},
    "化学制剂": {"enable": ["drug_ramp"]},
    "医疗耗材": {"enable": ["import_substitution"]},
    "医疗设备": {"enable": ["import_substitution"]},

    # ── 军工电子：军品交付恢复 ──
    "军工电子": {"enable": ["defense_recovery"]},

    # ── 软件：平台网络效应 ──
    "横向通用软件": {"enable": ["platform_network"]},
    # Sprint 20.1: 摘除 platform_network 自动启用 — 垂直软件 ≠ 一定有平台网络效应
    # 合合信息等 AI 工具/SaaS 工具走通用规则，真正平台型(金山办公)通过 sub_gene_map 附加标签
    "垂直应用软件": {},

    # ── 光模块豁免：rd 阈值替代（参数化） ──
    "通信网络设备及器件": {
        "special_logic": "optical_exemption",
        "tech_penetration": {
            "rd_ratio": None,       # 取消 3% 阈值
            "roic_min": 15,
        },
    },
    "光学元件": {
        "special_logic": "optical_exemption",
        "tech_penetration": {
            "rd_ratio": None,
            "roic_min": 15,
        },
    },
}


def get_industry_rules(industry_l3: str) -> dict:
    """获取指定行业的规则配置。无配置时返回空 dict。"""
    return INDUSTRY_RULES.get(industry_l3, {})


def is_optical_stock(code: str, industry_l3: str, stock_name: str = "") -> bool:
    """判定是否为光模块标的。

    L3 匹配 + (代码白名单 或 名称含关键词) 双重判定。
    避免「通信网络设备及器件」L3 内的基站设备商被误豁免。
    """
    rules = get_industry_rules(industry_l3)
    if rules.get("special_logic") != "optical_exemption":
        return False
    if code in OPTICAL_CODES:
        return True
    if stock_name:
        return any(kw in stock_name for kw in OPTICAL_NAME_KEYWORDS)
    return False
