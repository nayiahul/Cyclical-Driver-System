"""全局可配置常量"""

# 回测
INITIAL_CAPITAL = 100_000_000  # 初始资金 1亿
START_DATE = "20150101"
END_DATE = "20241231"

# 交易成本
COMMISSION_RATE = 0.0003   # 佣金
STAMP_TAX_RATE = 0.001     # 印花税（卖出）
SLIPPAGE_RATE = 0.0017     # 滑点
TOTAL_COST_RATE = COMMISSION_RATE + STAMP_TAX_RATE + SLIPPAGE_RATE  # 0.3%

# 组合约束
MAX_SINGLE_WEIGHT = 0.08   # 单票上限 8%
MIN_HOLDINGS = 15          # 最少持仓数
IPO_LOCK_DAYS = 20         # 新股上市后跳过交易日数

# 缓存
CACHE_DIR = "data/cache"
TRADE_CALENDAR_CACHE = "data/cache/trade_calendar.csv"
STOCK_LIST_CACHE = "data/cache/stock_list.csv"

# 输出
OUTPUT_DIR = "output"
