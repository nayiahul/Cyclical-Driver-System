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

# L0 Regime 防御权重矩阵（不按生命周期，全局统一）
# DEFENSE: 压低 L4/L5（行业趋势+预期差在熊市误导），拉高 L1/L3（排雷+资本效率）
# CAUTION: 中间态，比正常权重保守但不极端
REGIME_WEIGHTS = {
    "defensive": {
        "L1_risk": 0.25,
        "L2_moat": 0.15,
        "L3_efficiency": 0.40,
        "L4_industry": 0.10,
        "L5_expectation": 0.10,
    },
    "maturity_forced": {
        "L1_risk": 0.25,
        "L2_moat": 0.15,
        "L3_efficiency": 0.40,
        "L4_industry": 0.10,
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
    # 通信设备 — 硬件制造，研发费率 3-5% 正常
    "通信网络设备及器件": {
        "rd_intensity_high": 5.0,
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

# PEG 适用域 — 按行业增长驱动类型标注PEG可信度
# level: "valid"=PEG有效, "caution"=需注意假设, "misleading"=可能误导
PEG_CONFIDENCE = {
    # 技术扩散型 — PEG有效但需盯订单/CAPEX
    "半导体设备": {"level": "valid", "driver": "技术扩散型", "note": "PEG有效，需盯合同负债(订单先行)和CAPEX效率"},
    "半导体材料": {"level": "valid", "driver": "技术扩散型", "note": "PEG有效，需盯下游扩产周期"},
    "集成电路制造": {"level": "valid", "driver": "技术扩散型", "note": "PEG有效，需盯产能利用率和良率爬坡"},
    "集成电路封测": {"level": "valid", "driver": "技术扩散型", "note": "PEG有效，产能扩张周期需同步验证"},
    "通信网络设备及器件": {"level": "valid", "driver": "技术扩散型", "note": "PEG有效，需盯订单持续性(合同负债)和CAPEX效率"},
    "消费电子零部件及组装": {"level": "caution", "driver": "技术扩散型", "note": "PEG可用但需盯大客户周期，单一客户依赖风险"},
    "品牌消费电子": {"level": "caution", "driver": "品牌溢价型", "note": "PEG可用，品牌溢价可持续性是关键假设"},
    "军工电子": {"level": "valid", "driver": "订单驱动型", "note": "PEG有效，合同负债先行，需盯型号放量节奏"},
    "航空装备": {"level": "valid", "driver": "订单驱动型", "note": "PEG有效，合同负债是先行指标，需盯交付节奏"},
    "航天装备": {"level": "valid", "driver": "订单驱动型", "note": "PEG有效，合同负债先行，型号驱动增长"},
    "IT服务": {"level": "valid", "driver": "订阅转型型", "note": "PEG有效但需验证ARR/NDR续费率"},
    "垂直应用软件": {"level": "valid", "driver": "订阅转型型", "note": "PEG有效但需验证续费率(NDR>100%)和人效"},
    "医疗设备": {"level": "valid", "driver": "技术扩散型", "note": "PEG有效，国产替代+出海驱动，需盯海外收入占比"},
    # 周期价格型 — PEG可能误导，利润暴增不可持续
    "光伏电池组件": {"level": "misleading", "driver": "周期价格型", "note": "PEG可能严重误导，产能周期顶部利润暴增不可持续，建议参考PB/EVEBITDA"},
    "逆变器": {"level": "caution", "driver": "周期价格型", "note": "PEG需谨慎：光伏产业链周期敏感，增速波动大，需盯海外毛利率和市占率方向"},
    "锂电池": {"level": "misleading", "driver": "周期价格型", "note": "PEG可能严重误导，锂价/产能周期驱动利润波动，建议参考PB/EVEBITDA"},
    "有机硅": {"level": "misleading", "driver": "周期价格型", "note": "PEG可能严重误导，价格周期驱动利润波动剧烈"},
    "化工新材料": {"level": "caution", "driver": "周期价格型", "note": "PEG需谨慎，新材料有成长性但价格周期不可忽略"},
    # 品牌/消费型 — PEG有效但增速较慢
    "白酒": {"level": "valid", "driver": "品牌护城河型", "note": "PEG有效，品牌护城河支撑长期定价权，PEG>1.5仍可接受"},
    "啤酒": {"level": "valid", "driver": "品牌护城河型", "note": "PEG有效，产品结构升级驱动增长，PEG>1.5仍可接受"},
    # 创新药/器械 — PEG依赖盈利质量
    "化学制剂": {"level": "caution", "driver": "管线驱动型", "note": "PEG需谨慎：管线驱动型增长，研发资本化率影响利润质量，建议参考DCF"},
    "生物制品": {"level": "caution", "driver": "管线驱动型", "note": "PEG需谨慎：管线驱动型增长，需验证现金跑道和BD能力"},
    # 乘用车/汽配
    "乘用车": {"level": "caution", "driver": "周期价格型", "note": "周期敏感：电动化转型期PEG可用，但需盯单车均价和毛利率趋势"},
    "汽车电子电气系统": {"level": "valid", "driver": "技术扩散型", "note": "PEG有效，智能化渗透率提升驱动，需盯研发和定点项目"},
    # 成熟行业
    "空调": {"level": "valid", "driver": "成熟分红型", "note": "PEG有效但增长较慢，更多看现金流和分红"},
}

PEG_CONFIDENCE_DEFAULT = {"level": "caution", "driver": "通用框架", "note": "PEG基于「当前增速可持续」假设，需结合行业特征判断"}

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

# ===== 预过滤器参数 =====
PRE_FILTER = {
    # 第一层：基础清洗
    "require_fields": ["revenue_yoy", "gross_margin", "deducted_profit_yoy"],
    "exclude_sectors_l1": ["银行", "非银金融", "房地产"],
    "min_market_cap": 2.0,          # 最低市值(亿元)，壳价值以下

    # 第二层：Growth Signal Gate — 多路径 OR，全行业相对分位
    "route_a": {
        "revenue_pct_threshold": 0.4,  # 行业营收增速分位 > 40%（行业前60%）
    },
    "route_b": {
        "cl_ratio_pct_threshold": 0.4, # 合同负债/总资产 行业分位 > 40%
    },
    "route_c": {
        "roic_pct_threshold": 0.5,     # ROIC 行业分位 > 50%（行业上半区）
    },
}

# ===== 数据路径 =====
DATA_PATHS = {
    "tdx_cache": "data/cache/tdx_financials.csv",
    "stock_price_dir": "/Users/nayiahlu/Desktop/stocks",
    "sw_industry_map": "docs/sw_index_third_cons.csv",
    "output_dir": "output",
}
