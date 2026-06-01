"""Growth Source Classifier — 六维驱动力规则引擎。

识别增长来源: 技术渗透/份额提升/产品升级/产能释放/价格周期/低基数修复。
原则: 只做定性归因,不修改 Composite 分数。

Sprint 14: 新增ROIC历史波动率→周期顶部伪装检测。
Sprint 17: 直接消费漏斗预计算字段(rd_ratio, roic_ttm, gross_margin_trend, debt_ratio),
消除与快照层的重复计算和数据断层。
Sprint 18: capacity_expansion增加行业守卫(ASSET_HEAVY_L1) + quality_growth后备类别。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math

from .industry_template import get_industry_rules, is_optical_stock

# Sprint 18: 重资产行业白名单(申万一级行业) — capacity_expansion 仅在这些行业内触发
ASSET_HEAVY_L1 = {
    "电子", "机械设备", "电力设备", "国防军工", "基础化工",
    "有色金属", "钢铁", "建筑材料", "汽车", "石油石化",
    "煤炭", "公用事业", "交通运输", "建筑装饰",
}


def get_roic_volatility(code: str, t_date: str) -> float:
    """计算ROIC近5年max-min极差(pp)。>30pp→强周期信号。"""
    try:
        from growth_os.data import get_quarterly_series
        roic_q = get_quarterly_series(code, "roic", n_quarters=20, t_date=t_date).dropna()
        if len(roic_q) >= 8:
            return float(roic_q.max() - roic_q.min())
    except Exception:
        pass
    return 0.0


@dataclass
class GrowthAttribution:
    source: str           # tech_penetration/share_gain/product_upgrade/
                          # capacity_release/price_cycle/low_base_recovery/
                          # brand_premium/quality_growth
    confidence: float     # 0-1
    persistence: int      # 1-5 持续性评分
    evidence: list[str]   # 证据链
    risk_point: str       # 核心风险/失效条件
    narrative: str        # 一句话归因
    sub_gene: str = ""    # Sprint 20: 子基因标签(只读解释层,不参与评分)


def classify(row, gm_trend_label: str = "", roic_volatility: float = 0) -> GrowthAttribution:
    """六维驱动力分类器。

    优先使用漏斗预计算字段(rd_ratio, roic_ttm, gross_margin_trend, debt_ratio),
    回退到原始快照字段以保持向后兼容。

    row: dict-like, 来自漏斗结果行 + 快照原始字段的合并
    roic_volatility: ROIC近5年max-min极差(pp), >30pp触发强周期信号。
    """
    # ── 漏斗预计算字段(优先) ──
    rev_yoy = row.get("revenue_yoy") or 0
    rd_ratio = row.get("rd_ratio") or 0           # 漏斗已计算, 不再用 rd/revenue 重算
    roic = row.get("roic_ttm") or row.get("roic") or 0  # TTM ROIC 优先
    debt = row.get("debt_ratio") or row.get("debt_to_assets") or 0
    gm_trend = row.get("gross_margin_trend") or gm_trend_label

    # ── 原始快照字段(仅用于展示 + 漏斗未覆盖的比率) ──
    gm = row.get("gross_margin") or 0
    revenue = row.get("revenue") or 1
    fixed_assets = row.get("fixed_assets") or 0
    total_assets = row.get("total_assets") or 1
    selling_expense = row.get("selling_expense") or 0

    fixed_asset_ratio = fixed_assets / total_assets if total_assets > 0 else 0
    selling_ratio = (selling_expense / max(revenue, 1)) * 100

    # Sprint 18: 行业上下文
    industry_l1 = str(row.get("industry_l1", ""))
    is_asset_heavy = industry_l1 in ASSET_HEAVY_L1

    # Sprint 20: 行业模板规则
    industry_l3 = str(row.get("industry_l3", ""))
    stock_code = str(row.get("code", ""))
    stock_name = str(row.get("name", ""))
    industry_rules = get_industry_rules(industry_l3)
    disabled_genes = industry_rules.get("disable", [])
    enabled_genes = industry_rules.get("enable", [])
    fallback_gene = industry_rules.get("fallback_gene", "")
    is_optical = is_optical_stock(stock_code, industry_l3, stock_name)

    evidence = []
    sources = []

    gm_rising = "上升" in str(gm_trend)
    gm_falling = "下降" in str(gm_trend)

    # ── Sprint 14+16.1: 周期检测(高波动+低研发+GM下降→价格周期) ──
    # 成长性豁免: 高研发(>3%)+高增速(CAGR>30%)→爆发式成长,非周期
    cagr3_val = row.get("revenue_cagr_3y") or rev_yoy
    is_growth_exempt = (rd_ratio > 3 and (cagr3_val > 30 or rev_yoy > 50))
    # Sprint 20: 光模块豁免 — 即使低研发+高波动,也不判为价格周期
    is_growth_exempt = is_growth_exempt or is_optical
    if roic_volatility > 30 and rd_ratio < 5 and not is_growth_exempt:
        sources.append(("price_cycle", 0.92))
        evidence.append(f"ROIC 5年极差{roic_volatility:.0f}pp(>30pp)→强周期波动")
        evidence.append(f"研发仅{rd_ratio:.1f}%→非技术/产品驱动")
        return GrowthAttribution(
            source="price_cycle", confidence=0.92, persistence=2,
            evidence=evidence,
            risk_point="价格回落至周期底部,利润崩塌",
            narrative=f"价格周期(ROIC极差{roic_volatility:.0f}pp+研发{rd_ratio:.1f}%)。增长来自价格波动,非结构优势。"
        )
    # 高波动但有研发豁免 → 标记但不强判
    if roic_volatility > 30 and is_growth_exempt:
        evidence.append(f"ROIC极差{roic_volatility:.0f}pp但研发{rd_ratio:.1f}%→爆发成长,非周期")

    # ── Sprint 20: 行业专属基因优先匹配 ──
    rd_min = industry_rules.get("rd_threshold", 5.0)  # Sprint 20.2: 行业可覆盖默认 5%
    for gene in enabled_genes:
        if gene == "drug_ramp" and rd_ratio > 10 and rev_yoy > 20:
            sources.append(("drug_ramp", 0.90))
            evidence.append(f"药品放量驱动(高研发{rd_ratio:.1f}%+营收+{rev_yoy:.0f}%)")
        elif gene == "product_cycle" and rd_ratio > rd_min and rev_yoy > 20:
            sources.append(("product_cycle", 0.80))
            evidence.append(f"产品周期驱动(研发{rd_ratio:.1f}%+营收+{rev_yoy:.0f}%)")
        elif gene == "hit_game":
            if rd_ratio > rd_min and rev_yoy > 50:
                sources.append(("hit_game", 0.85))
                evidence.append(f"爆款游戏驱动(研发{rd_ratio:.1f}%+营收+{rev_yoy:.0f}%)")
            elif rd_ratio > rd_min:
                sources.append(("product_cycle", 0.75))
                evidence.append(f"游戏产品周期(研发{rd_ratio:.1f}%)")
        elif gene == "import_substitution" and roic > 10 and rev_yoy > 15:
            sources.append(("import_substitution", 0.75))
            evidence.append(f"国产替代驱动(ROIC={roic:.1f}%+营收+{rev_yoy:.0f}%)")
        elif gene == "defense_recovery" and rev_yoy > 20:
            sources.append(("defense_recovery", 0.80))
            evidence.append(f"军品恢复交付驱动(营收+{rev_yoy:.0f}%)")
        elif gene == "platform_network" and rev_yoy > 15 and roic > 10:
            sources.append(("platform_network", 0.75))
            evidence.append(f"平台网络效应驱动(营收+{rev_yoy:.0f}%+ROIC={roic:.1f}%)")
        elif gene in ("project_cycle", "real_estate_recovery") and rev_yoy > 5:
            sources.append((gene, 0.65))
            evidence.append(f"项目周期驱动(营收+{rev_yoy:.0f}%)")
        elif gene == "rental_growth" and rev_yoy > 5:
            sources.append(("rental_growth", 0.65))
            evidence.append(f"租金增长驱动(营收+{rev_yoy:.0f}%)")

    # ── 技术渗透 ──: GM扩张 + (光模块豁免 或 高研发) + 高ROIC
    if gm_rising and roic > 10 and "tech_penetration" not in disabled_genes:
        # Sprint 20: 光模块行业 rd 阈值豁免（读 industry_template 配置）
        tp_cfg = industry_rules.get("tech_penetration", {})
        rd_min = tp_cfg.get("rd_ratio", 3)
        roic_min = tp_cfg.get("roic_min", 10)
        if (is_optical or (rd_ratio > (rd_min or 3))) and roic > roic_min:
            sources.append(("tech_penetration", 0.85))
            evidence.append(f"毛利率{ gm_trend }(+{gm:.0f}%)")
            evidence.append(f"研发强度{rd_ratio:.1f}%")
            evidence.append(f"ROIC={roic:.1f}%")

    # ── 份额提升 ──: 营收高增 + GM稳定 + 销售费用率可能偏高
    if rev_yoy > 20 and (gm_rising or "稳定" in str(gm_trend)) and roic > 8:
        if "tech_penetration" not in dict(sources) and "share_gain" not in disabled_genes:
            sources.append(("share_gain", 0.70))
            evidence.append(f"营收+{rev_yoy:.0f}%但GM{ gm_trend }(非价格驱动)")
            evidence.append(f"ROIC={roic:.1f}%支持持续投入")

    # ── 产品升级 ──: GM扩张 + 中低研发 + 营收温和增长
    if gm_rising and rd_ratio < 5 and 5 < rev_yoy < 40:
        sources.append(("product_upgrade", 0.65))
        evidence.append(f"GM{ gm_trend }但研发仅{rd_ratio:.1f}%(非技术迭代)")
        evidence.append(f"营收+{rev_yoy:.0f}%温和,ASP驱动")

    # ── 产能释放 ──: 高固资 + CAPEX扩张 + GM稳 (仅重资产行业)
    if (fixed_asset_ratio > 0.25 or debt > 35) and rev_yoy > 10 and is_asset_heavy:
        if not gm_falling or roic > 8:
            sources.append(("capacity_expansion", 0.65))
            evidence.append(f"固资占比{fixed_asset_ratio:.0%}+营收+{rev_yoy:.0f}%→产能释放")
            if gm_falling:
                evidence.append("⚠️ GM下滑→产能过剩风险(可能失效中)")
    elif (fixed_asset_ratio > 0.25 or debt > 35) and rev_yoy > 10 and not is_asset_heavy:
        evidence.append(f"轻资产行业({industry_l1})高负债/高固资→非产能释放,跳过")

    # ── 品牌溢价 ──: 超高GM+极低销售费率+极低研发+温和增长
    if gm > 60 and selling_ratio < 15 and rd_ratio < 5 and 5 < rev_yoy < 30:
        sources.append(("brand_premium", 0.85))
        evidence.append(f"GM={gm:.0f}%极稳+销售费率仅{selling_ratio:.0f}%+研发{rd_ratio:.1f}%")
        evidence.append(f"营收+{rev_yoy:.0f}%温和→品牌定价权驱动")

    # ── 价格周期 ──: GM波动大 + 低研发 + 高资产周转
    if gm_falling and rd_ratio < 3 and roic < 10 and abs(rev_yoy) < 50:
        sources.append(("price_cycle", 0.90))
        evidence.append(f"GM{'上升' if gm_rising else '下降' if gm_falling else '稳定'}+研发{rd_ratio:.1f}%→非产品驱动")
        evidence.append(f"ROIC仅{roic:.1f}%→周期底部")

    # ── 低基数修复 ──: 极高增速 + GM不稳定 + 历史增速低
    if rev_yoy > 100 and roic < 15:
        if "tech_penetration" not in dict(sources) and "price_cycle" not in dict(sources):
            sources.append(("low_base_recovery", 0.55))
            evidence.append(f"营收+{rev_yoy:.0f}%异常高但ROIC仅{roic:.1f}%→低基数反弹")

    # ── Sprint 20: 行业基因兜底映射 ──（禁用后的标的用 fallback_gene）
    if not sources and fallback_gene:
        sources.append((fallback_gene, 0.50))
        evidence.append(f"行业兜底({industry_l3}禁用原基因→{fallback_gene})")

    # ── Sprint 18: 高质量成长后备 ──: 捕获落入规则间隙的高质量公司
    if not sources and roic > 15 and rev_yoy > 10:
        sources.append(("quality_growth", 0.50))
        evidence.append(f"ROIC={roic:.1f}%+研发{rd_ratio:.1f}%+增速{rev_yoy:.0f}%→高质量成长(驱动力待确认)")

    if not sources:
        return GrowthAttribution(
            source="unknown", confidence=0.3, persistence=3,
            evidence=[f"营收+{rev_yoy:.0f}%,GM={gm:.0f}%,ROIC={roic:.1f}%"],
            risk_point="需人工复核驱动力",
            narrative="驱动力不明确，建议查看年报/调研纪要进一步判断。"
        )

    # 选置信度最高的来源
    sources.sort(key=lambda x: -x[1])
    primary, conf = sources[0]

    # ── Sprint 20.1: 出口一致性校正 ──
    # Sprint 20.2: 仅当 enable 基因全部未命中时才触发
    # (若 enable 已命中, product_cycle/hit_game 置信度高于 share_gain, 校正不必要)
    _GENE_CORRECTIONS: dict[tuple[str, str], str] = {
        ("share_gain", "游戏"): "quality_growth",
        ("product_upgrade", "装修装饰"): "quality_growth",
    }
    correction_key = (primary, industry_l3)
    enable_hit = any(s[0] in enabled_genes for s in sources)
    if not enable_hit and correction_key in _GENE_CORRECTIONS:
        corrected = _GENE_CORRECTIONS[correction_key]
        evidence.append(f"一致性校正: {industry_l3}不适合{primary}→回退{corrected}")
        primary = corrected

    # 持续性评分
    persistence_map = {
        "tech_penetration": 5, "share_gain": 4, "product_upgrade": 4,
        "capacity_expansion": 3, "brand_premium": 5,
        "capacity_release": 3, "price_cycle": 2, "low_base_recovery": 1,
        "quality_growth": 3,
        # Sprint 20: 行业专属基因
        "drug_ramp": 4, "product_cycle": 3, "hit_game": 3,
        "import_substitution": 4, "defense_recovery": 3,
        "platform_network": 4, "project_cycle": 2,
        "real_estate_recovery": 2, "rental_growth": 3,
    }
    persistence = persistence_map.get(primary, 3)

    risk_map = {
        "tech_penetration": "渗透率接近天花板或技术路线切换",
        "share_gain": "份额争夺导致费用率失控",
        "product_upgrade": "ASP提升不可持续,消费降级风险",
        "capacity_expansion": "产能过剩导致ROIC下滑(GM趋势恶化→失效信号)",
        "brand_premium": "品牌老化或渠道堰塞湖(库存>年销2x)",
        "capacity_release": "产能过剩导致ROIC下滑",
        "price_cycle": "价格回落至周期底部,利润崩塌",
        "low_base_recovery": "基数效应消退后增速断崖",
        "quality_growth": "驱动力未确认,可能为技术渗透/产品升级/品牌溢价,需人工复核",
        "drug_ramp": "管线失败或竞品上市导致放量不及预期",
        "product_cycle": "产品老化/用户流失,新游/新品接力不成功",
        "hit_game": "爆款生命周期衰退,下一款产品不确定性高",
        "import_substitution": "国产替代空间收窄,技术差距被追赶",
        "defense_recovery": "军品订单周期性,交付节奏不可控",
        "platform_network": "平台用户增长见顶,网络效应消退",
        "project_cycle": "项目交付节奏波动,地产/基建周期影响",
        "real_estate_recovery": "地产复苏不及预期,政策收紧",
        "rental_growth": "租金增长见顶,空置率上升",
    }

    narrative_map = {
        "tech_penetration": f"技术渗透驱动(GM上升+高研发{rd_ratio:.1f}%)，增长来自新产品/新技术渗透率提升，可持续性强。",
        "share_gain": f"份额提升驱动(营收+{rev_yoy:.0f}%+ROIC={roic:.1f}%)，增长来自抢占竞争对手份额，可持续性取决于护城河深度。",
        "product_upgrade": f"产品升级驱动(GM上升+营收+{rev_yoy:.0f}%)，增长来自ASP提升/结构优化，需关注升级天花板。",
        "capacity_expansion": f"产能释放驱动(固资占比高+营收+{rev_yoy:.0f}%)，增长来自前期CAPEX转化为收入，需跟踪产能利用率。",
        "capacity_release": f"产能释放驱动(负债{debt:.0f}%+ROIC={roic:.1f}%)，增长来自前期CAPEX转化为收入，需跟踪产能利用率。",
        "brand_premium": f"品牌溢价驱动(GM={gm:.0f}%极稳+低费率)，增长来自品牌定价权+温和提价，可预测性极高。",
        "price_cycle": f"价格周期驱动(GM{ gm_trend }+零研发)，增长来自商品/服务价格上涨，不可持续。需用周期底部利润重估。",
        "low_base_recovery": f"低基数修复驱动(营收+{rev_yoy:.0f}%)，增长来自前期低基数反弹，不可持续。关注增速回归常态后的真实水平。",
        "quality_growth": f"高质量成长(ROIC={roic:.1f}%+研发{rd_ratio:.1f}%)，驱动力待进一步确认。建议查看年报/调研纪要。",
        "drug_ramp": f"药品放量驱动(高研发{rd_ratio:.1f}%+营收+{rev_yoy:.0f}%)，增长来自创新药上市后商业化爬坡，持续性好但需跟踪竞争格局。",
        "product_cycle": f"产品周期驱动(研发{rd_ratio:.1f}%+营收+{rev_yoy:.0f}%)，增长来自新游/新品上线爆发，需关注产品生命周期与接力能力。",
        "hit_game": f"爆款游戏驱动(研发{rd_ratio:.1f}%+营收+{rev_yoy:.0f}%)，增长来自单一爆款，持续性取决于下一款产品储备。",
        "import_substitution": f"国产替代驱动(ROIC={roic:.1f}%+营收+{rev_yoy:.0f}%)，增长来自替代进口份额，可持续性取决于技术差距与政策支持。",
        "defense_recovery": f"军品恢复交付驱动(营收+{rev_yoy:.0f}%)，增长来自军品订单恢复/新装备列装，持续性好但节奏受采购周期影响。",
        "platform_network": f"平台网络效应驱动(营收+{rev_yoy:.0f}%+ROIC={roic:.1f}%)，增长来自平台用户增长与网络效应强化，边际成本递减。",
        "project_cycle": f"项目周期驱动(营收+{rev_yoy:.0f}%)，增长来自在手订单交付，需关注新签订单与项目储备。",
        "real_estate_recovery": f"地产链修复驱动(营收+{rev_yoy:.0f}%)，增长来自地产后周期回暖，持续性取决于地产政策与销售趋势。",
        "rental_growth": f"租金增长驱动(营收+{rev_yoy:.0f}%)，增长来自租金上涨/新市场开业，稳定性较高但增速有限。",
    }

    # Sprint 20: 分配 sub_gene（只读解释层）
    sub_gene = assign_sub_gene(primary, industry_l3)

    return GrowthAttribution(
        source=primary, confidence=round(conf, 2), persistence=persistence,
        evidence=evidence,
        risk_point=risk_map.get(primary, "需人工复核"),
        narrative=narrative_map.get(primary, f"驱动力待确认。{'; '.join(evidence)}"),
        sub_gene=sub_gene,
    )


# ── Sprint 20: Sub-Gene 映射表（只读解释层） ──

SUB_GENE_MAP: dict[tuple[str, str], str] = {
    # tech_penetration → 行业子基因
    ("tech_penetration", "通信网络设备及器件"): "ai_optical_upgrade",
    ("tech_penetration", "光学元件"): "ai_optical_upgrade",
    ("tech_penetration", "其他生物制品"): "biologic_launch",
    ("tech_penetration", "化学制剂"): "drug_ramp",
    ("tech_penetration", "军工电子"): "defense_upgrade",
    ("tech_penetration", "工控设备"): "equipment_upgrade",
    # share_gain → 行业子基因
    ("share_gain", "横向通用软件"): "platform_substitution",
    # Sprint 20.2: 删除 ("share_gain", "垂直应用软件"): "platform_network"
    # 垂直软件 ≠ 一定有平台网络效应（合合信息是 AI OCR 工具）
    ("share_gain", "医疗耗材"): "import_substitution",
    ("share_gain", "医疗设备"): "import_substitution",
    ("share_gain", "其他电源设备"): "market_expansion",
    ("share_gain", "线缆部件及其他"): "market_expansion",
    # quality_growth → 行业子基因
    ("quality_growth", "游戏"): "product_cycle",
    ("quality_growth", "装修装饰"): "project_cycle",
    ("quality_growth", "商业物业经营"): "rental_growth",
    ("quality_growth", "跨境电商"): "platform_expansion",
    ("quality_growth", "通信终端及配件"): "product_upgrade",
    # product_cycle → 行业子基因
    ("product_cycle", "游戏"): "product_cycle",
    # product_upgrade → 行业子基因（郑中设计等）
    ("product_upgrade", "装修装饰"): "project_cycle",
    # hit_game → 行业子基因
    ("hit_game", "游戏"): "hit_game",
    # drug_ramp → 行业子基因
    ("drug_ramp", "其他生物制品"): "biologic_launch",
    ("drug_ramp", "化学制剂"): "drug_ramp",
    # project_cycle → 行业子基因
    ("project_cycle", "装修装饰"): "project_cycle",
    # share_gain → 游戏（后备）
    ("share_gain", "游戏"): "hit_game",
    # price_cycle → 行业子基因（备用）
    ("price_cycle", "通信网络设备及器件"): "ai_optical_cycle",
}


# Sprint 20.2: sub_gene 语义冲突防御 — 临时方案, Sprint 21 替换为 eligibility 机制
_SUB_GENE_CONFLICTS = {
    ("share_gain", "platform_network"),  # 份额抢夺 ≠ 平台网络效应
}


def assign_sub_gene(gene: str, industry_l3: str) -> str:
    """根据主基因和行业分配子基因。只读解释层，不影响评分/仓位。"""
    sub = SUB_GENE_MAP.get((gene, industry_l3), "")
    if (gene, sub) in _SUB_GENE_CONFLICTS:
        return ""  # Sprint 20.2: 宁可解释少，不能解释假
    return sub
