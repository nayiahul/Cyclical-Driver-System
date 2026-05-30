"""Growth Source Classifier — 六维驱动力规则引擎。

识别增长来源: 技术渗透/份额提升/产品升级/产能释放/价格周期/低基数修复。
原则: 只做定性归因,不修改 Composite 分数。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math


@dataclass
class GrowthAttribution:
    source: str           # tech_penetration/share_gain/product_upgrade/
                          # capacity_release/price_cycle/low_base_recovery
    confidence: float     # 0-1
    persistence: int      # 1-5 持续性评分
    evidence: list[str]   # 证据链
    risk_point: str       # 核心风险/失效条件
    narrative: str        # 一句话归因


def classify(stock: dict, gm_trend_label: str = "") -> GrowthAttribution:
    """六维驱动力分类器。输入财务快照行 + 毛利率趋势标签。"""
    rev_yoy = stock.get("revenue_yoy") or 0
    gm = stock.get("gross_margin") or 0
    rd = stock.get("rd_expense", 0) or 0
    revenue = stock.get("revenue", 0) or 1
    rd_ratio = rd / revenue * 100 if revenue > 0 else 0
    roic = stock.get("roic") or 0
    debt = stock.get("debt_to_assets") or 0

    gm_trend = gm_trend_label  # "上升"/"稳定"/"下降"

    evidence = []
    sources = []

    # ── 技术渗透 ──: GM扩张 + 高研发 + 高ROIC
    if gm_trend == "上升" and rd_ratio > 3 and roic > 10:
        sources.append(("tech_penetration", 0.85))
        evidence.append(f"毛利率{ gm_trend }(+{gm:.0f}%)")
        evidence.append(f"研发强度{rd_ratio:.1f}%")
        evidence.append(f"ROIC={roic:.1f}%")

    # ── 份额提升 ──: 营收高增 + GM稳定 + 销售费用率可能偏高
    if rev_yoy > 20 and gm_trend in ("上升", "稳定") and roic > 8:
        if "tech_penetration" not in dict(sources):
            sources.append(("share_gain", 0.70))
            evidence.append(f"营收+{rev_yoy:.0f}%但GM{ gm_trend }(非价格驱动)")
            evidence.append(f"ROIC={roic:.1f}%支持持续投入")

    # ── 产品升级 ──: GM扩张 + 中低研发 + 营收温和增长
    if gm_trend == "上升" and rd_ratio < 5 and 5 < rev_yoy < 40:
        sources.append(("product_upgrade", 0.65))
        evidence.append(f"GM{ gm_trend }但研发仅{rd_ratio:.1f}%(非技术迭代)")
        evidence.append(f"营收+{rev_yoy:.0f}%温和,ASP驱动")

    # ── 产能释放 ──: 高负债(>40%) + ROIC改善 + 营收加速
    if debt > 40 and roic > 8 and rev_yoy > 15:
        sources.append(("capacity_release", 0.60))
        evidence.append(f"高负债{debt:.0f}%+ROIC={roic:.1f}%→产能扩张期")
        evidence.append(f"营收+{rev_yoy:.0f}%,CAPEX转化中")

    # ── 价格周期 ──: GM波动大 + 低研发 + 高资产周转
    if gm_trend in ("下降",) and rd_ratio < 3 and roic < 10 and abs(rev_yoy) < 50:
        sources.append(("price_cycle", 0.90))
        evidence.append(f"GM{ gm_trend }+研发{rd_ratio:.1f}%→非产品驱动")
        evidence.append(f"ROIC仅{roic:.1f}%→周期底部")

    # ── 低基数修复 ──: 极高增速 + GM不稳定 + 历史增速低
    if rev_yoy > 100 and roic < 15:
        if "tech_penetration" not in dict(sources) and "price_cycle" not in dict(sources):
            sources.append(("low_base_recovery", 0.55))
            evidence.append(f"营收+{rev_yoy:.0f}%异常高但ROIC仅{roic:.1f}%→低基数反弹")

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
        "capacity_release": 3, "price_cycle": 2, "low_base_recovery": 1,
    }
    persistence = persistence_map.get(primary, 3)

    # 风险点
    risk_map = {
        "tech_penetration": "渗透率接近天花板或技术路线切换",
        "share_gain": "份额争夺导致费用率失控",
        "product_upgrade": "ASP提升不可持续,消费降级风险",
        "capacity_release": "产能过剩导致ROIC下滑",
        "price_cycle": "价格回落至周期底部,利润崩塌",
        "low_base_recovery": "基数效应消退后增速断崖",
    }

    # 叙事
    narrative_map = {
        "tech_penetration": f"技术渗透驱动(GM上升+高研发{rd_ratio:.1f}%)，增长来自新产品/新技术渗透率提升，可持续性强。",
        "share_gain": f"份额提升驱动(营收+{rev_yoy:.0f}%+ROIC={roic:.1f}%)，增长来自抢占竞争对手份额，可持续性取决于护城河深度。",
        "product_upgrade": f"产品升级驱动(GM上升+营收+{rev_yoy:.0f}%)，增长来自ASP提升/结构优化，需关注升级天花板。",
        "capacity_release": f"产能释放驱动(负债{debt:.0f}%+ROIC={roic:.1f}%)，增长来自前期CAPEX转化为收入，需跟踪产能利用率。",
        "price_cycle": f"价格周期驱动(GM{ gm_trend }+零研发)，增长来自商品/服务价格上涨，不可持续。需用周期底部利润重估。",
        "low_base_recovery": f"低基数修复驱动(营收+{rev_yoy:.0f}%)，增长来自前期低基数反弹，不可持续。关注增速回归常态后的真实水平。",
    }

    return GrowthAttribution(
        source=primary, confidence=round(conf, 2), persistence=persistence,
        evidence=evidence,
        risk_point=risk_map.get(primary, "需人工复核"),
        narrative=narrative_map.get(primary, f"驱动力待确认。{'; '.join(evidence)}")
    )
