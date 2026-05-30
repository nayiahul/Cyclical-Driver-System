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

    evidence = []
    sources = []

    gm_rising = "上升" in str(gm_trend)
    gm_falling = "下降" in str(gm_trend)

    # ── Sprint 14+16.1: 周期检测(高波动+低研发+GM下降→价格周期) ──
    # 成长性豁免: 高研发(>3%)+高增速(CAGR>30%)→爆发式成长,非周期
    cagr3_val = row.get("revenue_cagr_3y") or rev_yoy
    is_growth_exempt = (rd_ratio > 3 and (cagr3_val > 30 or rev_yoy > 50))
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

    # ── 技术渗透 ──: GM扩张 + 高研发 + 高ROIC
    if gm_rising and rd_ratio > 3 and roic > 10:
        sources.append(("tech_penetration", 0.85))
        evidence.append(f"毛利率{ gm_trend }(+{gm:.0f}%)")
        evidence.append(f"研发强度{rd_ratio:.1f}%")
        evidence.append(f"ROIC={roic:.1f}%")

    # ── 份额提升 ──: 营收高增 + GM稳定 + 销售费用率可能偏高
    if rev_yoy > 20 and (gm_rising or "稳定" in str(gm_trend)) and roic > 8:
        if "tech_penetration" not in dict(sources):
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

    # 持续性评分
    persistence_map = {
        "tech_penetration": 5, "share_gain": 4, "product_upgrade": 4,
        "capacity_expansion": 3, "brand_premium": 5,
        "capacity_release": 3, "price_cycle": 2, "low_base_recovery": 1,
        "quality_growth": 3,
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
    }

    return GrowthAttribution(
        source=primary, confidence=round(conf, 2), persistence=persistence,
        evidence=evidence,
        risk_point=risk_map.get(primary, "需人工复核"),
        narrative=narrative_map.get(primary, f"驱动力待确认。{'; '.join(evidence)}")
    )
