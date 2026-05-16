"""通达信 gpcw 财务数据字段映射表

适用版本: pytdx HistoryFinancialReader (gpcw*.dat 格式)
验证日期: 2026-05-16
来源: 通达信 V7.xx 金融终端 gpcw*.dat 文件结构

100 = 万元 (部分字段标注)
"""

# 字段定义: {变量名: (col编号, 描述, 单位, 校验规则)}
TDX_FIELDS = {
    # ==================== S1 利润加速度所需 ====================
    "deducted_profit_yoy": {
        "col": 191,
        "desc": "扣除非经常性损益后的净利润同比增长率",
        "unit": "%",
        "valid_range": (-500, 500),  # 异常值截断范围
    },
    "deducted_profit_q": {
        "col": 233,
        "desc": "扣除非经常性损益后的净利润(单季度)",
        "unit": "元",
    },
    "revenue_yoy": {
        "col": 183,
        "desc": "营业收入同比增长率",
        "unit": "%",
        "valid_range": (-100, 500),
    },
    "operating_profit": {
        "col": 86,
        "desc": "营业利润",
        "unit": "元",
    },
    "operating_cash_flow": {
        "col": 107,
        "desc": "经营活动产生的现金流量净额",
        "unit": "元",
    },
    "accounts_receivable": {
        "col": 11,
        "desc": "应收账款",
        "unit": "元",
    },
    "revenue": {
        "col": 74,
        "desc": "营业收入",
        "unit": "元",
    },
    "income_tax": {
        "col": 93,
        "desc": "所得税费用",
        "unit": "元",
    },
    "total_profit": {
        "col": 92,
        "desc": "利润总额",
        "unit": "元",
    },

    # ==================== S2 产能扩张所需 ====================
    "contract_liabilities": {
        "col": 434,
        "desc": "合同负债",
        "unit": "万元",
        "note": "col434 原始单位为万元，使用时需×10000转元",
    },
    "advance_receipts": {
        "col": 45,
        "desc": "预收款项",
        "unit": "元",
    },
    "fixed_assets": {
        "col": 27,
        "desc": "固定资产",
        "unit": "元",
    },
    "capex_cash": {
        "col": 114,
        "desc": "购建固定资产、无形资产和其他长期资产支付的现金",
        "unit": "元",
    },
    "construction_in_progress": {
        "col": 26,
        "desc": "在建工程",
        "unit": "元",
    },
    "total_assets": {
        "col": 40,
        "desc": "资产总计",
        "unit": "元",
    },
    "inventory": {
        "col": 17,
        "desc": "存货",
        "unit": "元",
    },
    "contract_assets": {
        "col": 435,
        "desc": "合同资产",
        "unit": "万元",
    },

    # ==================== 备用/辅助 ====================
    "roe": {
        "col": 6,
        "desc": "净资产收益率(摊薄)",
        "unit": "%",
    },
    "gross_margin": {
        "col": 202,
        "desc": "销售毛利率",
        "unit": "%",
    },
    "rd_expense": {
        "col": 304,
        "desc": "研发费用",
        "unit": "元",
    },
}

# 用于校验的关键列（必须非空率 > 90%）
CRITICAL_COLS = [
    ("col191", "扣非净利润同比"),
    ("col233", "扣非净利润单季度"),
    ("col434", "合同负债"),
]

# Winsorize 阈值
WINSORIZE_MIN = 1   # 百分位
WINSORIZE_MAX = 99  # 百分位

# 低基数过滤: 去年同季度扣非净利润 < 此值 → 排除同比信号
MIN_BASE_PROFIT = 10_000_000  # 1000万元
