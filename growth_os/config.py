"""框架参数集中管理：阈值、权重矩阵、行业翻译表。

所有可调参数集中于此，不散落在其他模块中。
"""
from enum import Enum


class LifecycleStage(Enum):
    INTRODUCTION = "导入期"
    ACCELERATION = "加速期"
    MATURITY = "成熟期"
    DECLINE = "衰退期"


# ===== 生命周期判定阈值 =====
LIFECYCLE_RULES = {
    "introduction": {
        "min_revenue": 0,              # 营收>0
        "min_net_margin": 3.0,         # 净利率<3%视为微利(非金融)
        "revenue_growth_above_median": True,  # 营收增速高于行业中位数
    },
    "acceleration": {
        "min_revenue_cagr_3y": 15.0,   # 营收3年CAGR>15%
        "deducted_vs_revenue_ratio": 1.0,  # 扣非增速>=营收增速
        "gross_margin_no_decline": True,   # 毛利率不下降
        "roic_improving": True,            # ROIC提升
    },
    "maturity": {
        "roic_above_wacc": True,       # ROIC > WACC
        "fcf_positive": True,           # FCF为正
        "revenue_growth_stable": 15.0,  # 增速<15%但>0
    },
    "decline": {
        "gross_margin_decline_quarters": 2,  # 毛利率连续N季下滑
        "roic_below_wacc": True,
    },
}

# ===== 动态权重矩阵 =====
WEIGHT_MATRIX = {
    LifecycleStage.INTRODUCTION: {
        "L1_risk": 0.10,
        "L2_moat": 0.30,
        "L3_efficiency": 0.10,
        "L4_industry": 0.35,
        "L5_expectation": 0.15,
    },
    LifecycleStage.ACCELERATION: {
        "L1_risk": 0.20,
        "L2_moat": 0.30,
        "L3_efficiency": 0.25,
        "L4_industry": 0.15,
        "L5_expectation": 0.10,
    },
    LifecycleStage.MATURITY: {
        "L1_risk": 0.15,
        "L2_moat": 0.20,
        "L3_efficiency": 0.40,
        "L4_industry": 0.15,
        "L5_expectation": 0.10,
    },
}

# ===== L1 排雷阈值 =====
L1_THRESHOLDS = {
    "revenue_cagr_3y_min": 10.0,         # 营收3年CAGR下限(%) — 成熟期公司10%已属健康
    "deducted_vs_revenue_min_ratio": 0.5, # 扣非增速/营收增速下限 — 容忍短期背离
    "ocf_profit_ratio_3y_min": 0.6,       # OCF/净利润3年均值下限
    "receivable_surge_ratio": 1.5,        # 应收增速/营收增速上限
    "inventory_surge_ratio": 1.5,         # 存货增速/营收增速上限
    "goodwill_equity_max": 0.3,           # 商誉/净资产上限
    "max_red_flags": 3,                   # 允许最多2个红灯, ≥3淘汰
}

# ===== L2 护城河评分参数 =====
L2_SCORING = {
    "gross_margin_up_weight": 3.0,       # 毛利率上升满分3
    "gross_margin_stable_weight": 1.5,   # 毛利率稳定半满分
    "expense_leverage_weight": 2.0,      # 费用率摊薄满分2
    "rd_intensity_weight": 2.0,          # 研发强度满分2
    "contract_liab_weight": 2.0,         # 合同负债先行满分2
    "revenue_accel_weight": 1.0,         # 二阶导数满分1
    "l2_max_score": 10.0,
}

# ===== L3 资本效率评分参数 =====
L3_SCORING = {
    "roic_wacc_spread_excellent": 5.0,   # ROIC-WACC>5%满分
    "roic_wacc_positive_ok": 0.0,        # >0及格
    "roe_excellent": 20.0,              # ROE>20%满分
    "roe_good": 15.0,                    # ROE>15%及格
    "debt_ratio_safe": 30.0,            # 有息负债率<30%
    "interest_coverage_safe": 5.0,       # 利息保障>5x
    "l3_max_score": 10.0,
}

# ===== L4 行业翻译器 =====
# 按申万三级行业校准通用指标阈值
INDUSTRY_ADJUSTMENTS = {
    # 半导体/设备 — 存货增长可能是主动备产
    "半导体设备": {
        "inventory_growth_threshold": 2.0,
        "capex_positive_good": True,
        "rd_intensity_high": 15.0,
    },
    "半导体材料": {
        "inventory_growth_threshold": 2.0,
        "rd_intensity_high": 10.0,
    },
    "集成电路制造": {
        "inventory_growth_threshold": 2.0,
        "capex_positive_good": True,
        "rd_intensity_high": 12.0,
    },
    "集成电路封测": {
        "inventory_growth_threshold": 1.5,
        "rd_intensity_high": 8.0,
    },
    # 消费电子 — 毛利率敏感
    "消费电子零部件及组装": {
        "gross_margin_sensitive": True,
        "inventory_growth_threshold": 1.2,
    },
    "品牌消费电子": {
        "gross_margin_sensitive": True,
        "inventory_growth_threshold": 1.2,
    },
    # 白酒 — 预收款/合同负债极重要
    "白酒": {
        "advance_receipts_weight": 1.5,
        "inventory_growth_threshold": 1.5,
        "gross_margin_expected_high": 60.0,
    },
    "啤酒": {
        "advance_receipts_weight": 1.2,
        "gross_margin_expected_high": 35.0,
    },
    # 创新药/器械 — 高研发, 容忍亏损
    "化学制剂": {
        "rd_intensity_high": 15.0,
        "profit_tolerance": True,
    },
    "生物制品": {
        "rd_intensity_high": 15.0,
        "profit_tolerance": True,
    },
    "医疗设备": {
        "rd_intensity_high": 10.0,
        "profit_tolerance": True,
    },
    # SaaS/软件
    "IT服务": {
        "rd_intensity_high": 10.0,
        "advance_receipts_weight": 1.3,
    },
    "垂直应用软件": {
        "rd_intensity_high": 12.0,
        "advance_receipts_weight": 1.3,
    },
    # 新能源
    "光伏电池组件": {
        "capex_positive_good": True,
        "inventory_growth_threshold": 2.5,
    },
    "锂电池": {
        "capex_positive_good": True,
        "inventory_growth_threshold": 2.5,
    },
    # 军工 — 合同负债=订单先行
    "航空装备": {
        "advance_receipts_weight": 1.5,
    },
    "军工电子": {
        "advance_receipts_weight": 1.3,
    },
    "航天装备": {
        "advance_receipts_weight": 1.5,
    },
}

# 金融/地产行业（S2 等信号需要排除的行业）
EXCLUDED_INDUSTRIES_L1 = {"银行", "证券", "保险", "房地产开发", "房地产服务"}

# 哪些行业允许在建工程大增（资本密集型扩张正常）
CAPEX_HEAVY_INDUSTRIES = {
    "半导体设备", "集成电路制造", "光伏电池组件", "锂电池",
    "航空装备", "航天装备", "化工新材料", "有机硅",
}

# ===== L5 预期差评分参数 =====
L5_SCORING = {
    "peg_undervalued": 1.5,        # PEG<1.5低估
    "peg_fair": 2.5,               # PEG 1.5-2.5合理
    "peg_overvalued": 3.0,         # PEG>3高估
    "pe_percentile_low": 30.0,     # PE分位<30%偏低
    "pe_percentile_high": 70.0,    # PE分位>70%偏高
    "l5_max_score": 10.0,
}

# ===== WACC 参数 =====
WACC_CONFIG = {
    "beta_window_days": 504,         # Beta回归窗口(≈24个月交易日)
    "erp_damodaran_default": 5.5,    # Damodaran A股ERP参考值(%)
    "erp_method": "blend",           # "earnings_yield" | "damodaran" | "blend"
    "risk_free_maturity": "10年",    # 国债期限
    "min_market_cap": 1e9,           # 最小市值(10亿) skip太小的
}

# ===== 数据路径 =====
DATA_PATHS = {
    "tdx_cache": "data/cache/tdx_financials.csv",
    "stock_price_dir": "/Users/nayiahlu/Desktop/stocks",
    "sw_industry_map": "docs/sw_index_third_cons.csv",
    "output_dir": "output",
}
