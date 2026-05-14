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

# ============================================================
# 市场周期判定阈值
# ============================================================

# 极端快速通道
INDEX_DROP_20D = 0.15        # 指数急跌：20交易日跌幅 > 15%
MARGIN_WEEKLY_DROP = -0.10   # 流动性枯竭：融资余额单周变化 < -10%
V_REBOUND_10D = 0.12         # V型反转：10交易日反弹 > 12%

# 常规判定 — 牛市阈值
BREADTH_BULL = 0.55          # 广度(代理)：指数>MA20占比 > 55%
NEW_HIGH_BULL = 0.05         # 创新高(代理)：指数距52周高点 < 5%
PE_CHANGE_BULL = 0.0         # 风险偏好：PE 60日变化 > 0

# 常规判定 — 熊市阈值
BREADTH_BEAR = 0.40          # 广度(代理)：指数>MA20占比 < 40%
NEW_HIGH_BEAR = 0.15         # 创新高(代理)：指数距52周高点 > 15%
PE_CHANGE_BEAR = -0.05       # 风险偏好：PE 60日变化 < -5%

# 状态切换
BULL_VOTE = 3                # 牛市最少命中项数（指数/广度/新高/风险偏好/流动性 共5项）
STRUCT_TO_BULL_CONFIRM = 2   # 结构→牛市需连续确认月数
BEAR_WEEKLY_CONFIRM = 4      # 熊市需维持周数

# 仓位映射
POSITION_CAP = {"BULL": 1.0, "STRUCT": 1.0, "BEAR": 0.6}
