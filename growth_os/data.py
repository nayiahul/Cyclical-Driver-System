"""数据加载层 — 统一读取 TDX 财务缓存 + 日线行情 + 申万行业。

Growth OS 的数据唯一入口。所有模块通过此层获取数据，
隔离底层文件格式和路径细节。
"""
import os
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional
from loguru import logger
import akshare as ak

from growth_os.config import DATA_PATHS, WACC_CONFIG
from data_governance import filter_available_reports  # Gate 4: 披露日治理（P0-2）

# 缓存
_tdx_cache: Optional[pd.DataFrame] = None
_industry_map: Optional[dict] = None
_price_cache: dict = {}
_risk_free_rate: Optional[float] = None
_csi300_pe: Optional[float] = None


# ============================================================
# 1. TDX 财务数据
# ============================================================

def load_tdx_financials(force_reload: bool = False) -> pd.DataFrame:
    """加载 TDX 财务缓存 DataFrame。"""
    global _tdx_cache
    if _tdx_cache is not None and not force_reload:
        return _tdx_cache
    path = DATA_PATHS["tdx_cache"]
    if not os.path.exists(path):
        raise FileNotFoundError(f"TDX 缓存不存在: {path}，请先运行 tdx_financials.py")
    _tdx_cache = pd.read_csv(path)
    _tdx_cache["code"] = _tdx_cache["code"].astype(str).str.zfill(6)
    _tdx_cache["report_date_str"] = _tdx_cache["report_date_str"].astype(str)
    logger.info(f"TDX 缓存加载: {len(_tdx_cache)} 行, {_tdx_cache.code.nunique()} 只股票")
    return _tdx_cache


_snapshot_cache: dict = {}

def get_financial_snapshot(t_date: str) -> pd.DataFrame:
    """获取截至 t_date 的最新财务数据快照（带缓存）。

    Gate 4 (P0-2 修复): 从 report_date <= t 升级为披露日治理
    (filter_available_reports: 实际披露日 → 法定截止日 fallback)。
    """
    if t_date in _snapshot_cache:
        return _snapshot_cache[t_date]

    df = load_tdx_financials()
    df = filter_available_reports(df, t_date)  # Gate 4: 披露日语义
    snapshot = df.sort_values("report_date_str").groupby("code").tail(1).copy()
    _snapshot_cache[t_date] = snapshot
    logger.info(f"财务快照 {t_date}: {len(snapshot)} 只股票")
    return snapshot


_quarterly_cache: dict = {}
_roic_ttm_cache: dict = {}  # {(code, t_date): roic_ttm}

def get_quarterly_series(code: str, field: str, n_quarters: int = 12,
                         t_date: Optional[str] = None) -> pd.Series:
    """获取单只股票某字段的季度时间序列（最近 n_quarters 期）。

    Returns:
        Series index=report_date_str, values=field
    """
    cache_key = (code, field, t_date)
    if cache_key in _quarterly_cache:
        return _quarterly_cache[cache_key].tail(n_quarters)

    df = load_tdx_financials()
    if t_date:
        # Gate 4: 披露日语义（仅保留截至 t_date 已披露的报告，P0-2 修复）
        avail = filter_available_reports(df, t_date)
        df = avail
    mask = df["code"] == code
    series = df[mask].sort_values("report_date_str").set_index("report_date_str")[field]
    _quarterly_cache[cache_key] = series
    return series.tail(n_quarters)


def get_yoy_growth(code: str, field: str, t_date: str) -> float | None:
    """计算某字段的同比增速。

    同比 = (最近4季合计 / 去年同期4季合计 - 1) * 100
    """
    series = get_quarterly_series(code, field, n_quarters=8, t_date=t_date)
    if len(series) < 8:
        return None
    current_4q = series.iloc[-4:].sum()
    prev_4q = series.iloc[:4].sum()
    if prev_4q <= 0:
        return None
    return (current_4q / prev_4q - 1) * 100


def compute_revenue_cagr_3y(code: str, t_date: str) -> float | None:
    """用绝对营收(TTM)计算3年CAGR。

    从 cumulative revenue 反推单季度营收 →
    TTM = sum(最近4季单季营收) →
    CAGR = (TTM_now / TTM_3y_ago)^(1/3) - 1
    """
    rev_cum_series = get_quarterly_series(
        code, "revenue", n_quarters=20, t_date=t_date
    ).dropna()
    if len(rev_cum_series) < 12:
        return None

    # cumulative revenue → 单季度 revenue
    q_rev = []
    rev_vals = rev_cum_series.values
    dates = [str(d) for d in rev_cum_series.index.tolist()]
    prev = 0.0
    for d, v in zip(dates, rev_vals):
        if "0331" in d:
            q = v          # Q1 单季 = 当期累计值
            prev = v
        elif "0630" in d:
            q = v - prev   # Q2 = H1 - Q1
            prev = v
        elif "0930" in d:
            q = v - prev   # Q3 = 9M - H1
            prev = v
        elif "1231" in d:
            q = v - prev   # Q4 = FY - 9M
            prev = 0.0     # reset for new fiscal year
        else:
            continue
        if q > 0:
            q_rev.append(q)

    if len(q_rev) < 12:
        return None

    ttm_now = sum(q_rev[-4:])
    ttm_3y = sum(q_rev[-16:-12]) if len(q_rev) >= 16 else None

    if ttm_3y and ttm_3y > 0:
        return ((ttm_now / ttm_3y) ** (1 / 3) - 1) * 100
    return None


# ============================================================
# 1b. TTM ROIC 计算
# ============================================================

def de_cumulate_series(series: pd.Series) -> list[float]:
    """将累计值序列拆解为单季度值。

    TDX 利润表字段（revenue/operating_profit 等）按报告期累计：
      - 0331: Q1 单季值
      - 0630: H1 累计值 → Q2 = 0630 - 0331
      - 0930: 9M 累计值 → Q3 = 0930 - 0630
      - 1231: FY 累计值 → Q4 = 1231 - 0930

    Returns:
        单季度值列表，长度与输入相同（无法拆解的项为 None）。
        例如输入 8 个累计值 → 输出 8 个单季值。
    """
    vals = series.values
    dates = [str(d) for d in series.index.tolist()]
    result = []
    prev = 0.0
    for d, v in zip(dates, vals):
        if pd.isna(v):
            result.append(None)
            continue
        if "0331" in d:
            q = v
            prev = v
        elif "0630" in d:
            q = v - prev
            prev = v
        elif "0930" in d:
            q = v - prev
            prev = v
        elif "1231" in d:
            q = v - prev
            prev = 0.0
        else:
            q = None
        result.append(q if q is not None and q > 0 else (0.0 if q is not None else None))
    return result


def compute_invested_capital(row) -> float | None:
    """从快照行计算 Invested Capital。

    IC = 短期借款 + 长期借款 + 应付债券 + 一年内到期非流动负债
       + 租赁负债 + 归母权益

    任一必需字段缺失则返回 None。
    """
    fields = ["short_term_loan", "long_term_loan", "bonds_payable",
              "noncurrent_liab_due_1y", "lease_liability", "equity_parent"]
    total = 0.0
    for f in fields:
        v = row.get(f)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        total += float(v)
    return total if total > 0 else None


def compute_roic_ttm(code: str, t_date: str) -> float | None:
    """计算 TTM ROIC（Trailing Twelve Months 投入资本回报率）。

    步骤：
    1. 取 8 季 operating_profit 累计序列 → 拆解为单季值
    2. 取 8 季 invested capital 各字段 → 计算每季末 IC
    3. TTM NOPAT = sum(最近4季单季OP) × (1 - 25%)
    4. 平均 IC = (4季前IC + 最新IC) / 2
    5. TTM ROIC = TTM NOPAT / 平均 IC × 100

    Returns:
        TTM ROIC (%)，数据不足则返回 None。
    """
    cache_key = (code, t_date)
    if cache_key in _roic_ttm_cache:
        return _roic_ttm_cache[cache_key]

    # 1. 单季 operating_profit
    op_series = get_quarterly_series(code, "operating_profit",
                                     n_quarters=8, t_date=t_date).dropna()
    if len(op_series) < 6:
        _roic_ttm_cache[cache_key] = None
        return None
    single_q = de_cumulate_series(op_series)
    valid_q = [q for q in single_q[-4:] if q is not None]
    if len(valid_q) < 3:
        _roic_ttm_cache[cache_key] = None
        return None

    ttm_nopat = sum(valid_q) * 0.75  # tax_rate = 25%

    # 2. 每季 invested capital
    ic_fields = ["short_term_loan", "long_term_loan", "bonds_payable",
                 "noncurrent_liab_due_1y", "lease_liability", "equity_parent"]
    ic_series = {}
    for f in ic_fields:
        s = get_quarterly_series(code, f, n_quarters=8, t_date=t_date)
        if len(s.dropna()) < 4:
            _roic_ttm_cache[cache_key] = None
            return None  # IC 数据不足，无法计算
        ic_series[f] = s

    # 对齐日期索引，逐季计算 IC
    common_idx = op_series.index
    ic_vals = []
    for i, d in enumerate(common_idx):
        row = {f: ic_series[f].reindex(common_idx).iloc[i] for f in ic_fields}
        ic = compute_invested_capital(row)
        if ic is not None:
            ic_vals.append(ic)

    if len(ic_vals) < 4:
        _roic_ttm_cache[cache_key] = None
        return None

    # 平均 IC = (4季前 + 最新) / 2
    ic_begin = ic_vals[-min(5, len(ic_vals))]
    ic_end = ic_vals[-1]
    avg_ic = (ic_begin + ic_end) / 2

    if avg_ic <= 0:
        _roic_ttm_cache[cache_key] = None
        return None

    result = round(ttm_nopat / avg_ic * 100, 1)
    _roic_ttm_cache[cache_key] = result
    return result


# ============================================================
# 2. 申万行业
# ============================================================

def load_industry_map(force_reload: bool = False) -> dict:
    """加载申万三级行业映射 {code: industry_l3_name}。"""
    global _industry_map
    if _industry_map is not None and not force_reload:
        return _industry_map
    path = DATA_PATHS["sw_industry_map"]
    df = pd.read_csv(path, dtype={"证券代码": str})
    # 去除行业名称中的罗马数字后缀 (如 "白酒Ⅲ" → "白酒")
    def _clean_l3(name):
        if isinstance(name, str):
            for suffix in ["Ⅲ", "Ⅱ", "Ⅰ", "IV", "V"]:
                if name.endswith(suffix):
                    return name[:-len(suffix)]
        return name
    _industry_map = {}
    for code, name in zip(df["证券代码"], df["申万3级行业名称"]):
        _industry_map[code] = _clean_l3(name)
    logger.info(f"行业映射: {len(_industry_map)} 只")
    return _industry_map


def get_industry(code: str) -> str:
    """获取股票申万三级行业名。"""
    m = load_industry_map()
    return m.get(code, "未知")


# ============================================================
# 3. 日线行情
# ============================================================

def _code_to_filename(code: str) -> str:
    """将纯数字代码转为缓存文件名。"""
    return f"{code}.csv"


def _to_tx_symbol(code: str) -> str:
    """纯数字代码 → 腾讯格式 symbol。'000001'→'sz000001', '600519'→'sh600519'。"""
    if code.startswith(("0", "3")):
        return f"sz{code}"
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("4", "8", "9")):
        return f"bj{code}"
    return f"sz{code}"


def get_price_data(code: str) -> pd.DataFrame | None:
    """获取单只股票的日线行情 DataFrame。

    优先读本地缓存，缺失时从 akshare 下载。

    Columns: date, open, high, low, close, preclose, volume, amount,
             adjustflag, turn, tradestatus, pctChg, peTTM, pbMRQ, psTTM, pcfNcfTTM, isST
    """
    global _price_cache
    if code in _price_cache:
        return _price_cache[code]

    # 优先级：用户桌面文件（列最全，含peTTM） > 项目缓存目录（2014+完整历史） > akshare 下载
    fname = _code_to_filename(code)
    fpath = os.path.join(DATA_PATHS["stock_price_dir"], fname)
    if os.path.exists(fpath):
        try:
            df = pd.read_csv(fpath, parse_dates=["date"])
            max_date = df["date"].max()
            staleness = (pd.Timestamp.now() - max_date).days
            if staleness > 3:
                logger.warning(f"Desktop 行情缓存过期 {code}: 最新 {max_date.date()}, 已 {staleness} 天")
            _price_cache[code] = df
            return df
        except Exception:
            pass

    cache_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "cache", "daily_prices")
    cache_path = os.path.join(cache_dir, f"{code}.csv")
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, dtype={"date": str})
            df["date"] = pd.to_datetime(df["date"])
            # 若最新日期滞后超过7天，删除过期缓存触发akshare重下载
            max_date = df["date"].max()
            if (pd.Timestamp.now() - max_date).days > 7:
                os.remove(cache_path)
            else:
                _price_cache[code] = df
                return df
        except Exception:
            pass

    # 最后备选：akshare 下载
    try:
        import akshare as ak
        os.makedirs(cache_dir, exist_ok=True)
        symbol = _to_tx_symbol(code)
        hist = ak.stock_zh_a_hist_tx(
            symbol=symbol, start_date="20140101", end_date="20261231",
            adjust="qfq")
        df = hist[["日期", "收盘"]].copy()
        df = df.rename(columns={"日期": "date", "收盘": "close"})
        df["date"] = pd.to_datetime(df["date"])
        df.to_csv(cache_path, index=False)
        _price_cache[code] = df
        return df
    except Exception:
        return None


def get_market_cap(code: str, t_date: str) -> float | None:
    """估算市值 = 收盘价 × 总股本（从TDX）。"""
    price_df = get_price_data(code)
    if price_df is None:
        return None
    fin_df = get_financial_snapshot(t_date)
    row = fin_df[fin_df["code"] == code]
    if row.empty or pd.isna(row["total_shares"].iloc[0]):
        return None

    t_date_dt = pd.Timestamp(t_date)
    price_df = price_df[price_df["date"] <= t_date_dt]
    if price_df.empty:
        return None

    close = price_df.iloc[-1]["close"]
    shares = row["total_shares"].iloc[0]
    return close * shares


def get_pe_ttm(code: str, t_date: str) -> float | None:
    """获取 PE TTM（来自日线行情文件）。"""
    df = get_price_data(code)
    if df is None:
        return None
    t_dt = pd.Timestamp(t_date)
    df = df[df["date"] <= t_dt]
    try:
        last_pe = df.iloc[-1]["peTTM"]
    except KeyError:
        # akshare 下载的数据无 peTTM 列，回退到从 snapshot 估算
        snap = get_financial_snapshot(t_date)
        row = snap[snap["code"] == code]
        if row.empty:
            return None
        mc = get_market_cap(code, t_date)
        np_profit = row.iloc[0].get("deducted_profit_ttm")
        if mc and np_profit and not pd.isna(np_profit) and np_profit > 0:
            return float(mc / np_profit)
        return None
    if pd.isna(last_pe) or last_pe <= 0:
        return None
    return last_pe


# ============================================================
# 4. 无风险利率 & 市场数据
# ============================================================

def get_risk_free_rate() -> float:
    """获取10年期国债收益率作为无风险利率。

    Returns:
        年化收益率（例如 1.46 = 1.46%）
    """
    global _risk_free_rate
    if _risk_free_rate is not None:
        return _risk_free_rate
    try:
        df = ak.bond_zh_us_rate()
        col_10y = "中国国债收益率10年"
        if col_10y in df.columns:
            _risk_free_rate = float(df[col_10y].iloc[-1])
            logger.info(f"无风险利率(10Y国债): {_risk_free_rate:.2f}%")
        else:
            _risk_free_rate = 1.5
            logger.warning(f"bond_zh_us_rate 缺少10年期列，使用默认值1.5%")
    except Exception as e:
        logger.warning(f"AKShare 获取国债收益率失败: {e}，使用默认值1.5%")
        _risk_free_rate = 1.5
    return _risk_free_rate


def get_csi300_pe_ttm() -> float:
    """获取沪深300 PE TTM，用于 WACC/ERP 计算。

    直接取 CSI300 指数 PE，经 sanity check 后使用。
    若 PE 极端失真（<8 或 >25），回退到长期中位数 14.5。
    """
    global _csi300_pe
    if _csi300_pe is not None:
        return _csi300_pe
    try:
        df = ak.stock_market_pe_lg(symbol="沪深300")
        raw_pe = float(df["市盈率"].iloc[-1])
        if 8 <= raw_pe <= 25:
            _csi300_pe = round(raw_pe, 1)
            logger.info(f"沪深300 PE(TTM): {_csi300_pe:.1f}")
        else:
            _csi300_pe = 14.5
            logger.warning(f"沪深300 PE={raw_pe:.1f} 超出合理区间[8,25]，"
                           f"使用长期中位数{_csi300_pe}")
    except Exception as e:
        logger.warning(f"获取CSI300 PE失败: {e}，使用默认值14.5")
        _csi300_pe = 14.5
    return _csi300_pe


# ============================================================
# 5. GrowthOS 统一数据快照
# ============================================================

def load_growth_data(t_date: str) -> pd.DataFrame:
    """加载 Growth OS 所需的完整合并数据。

    合并 TDX 财务快照 + 行情估值 + 申万行业。
    """
    fin = get_financial_snapshot(t_date)
    ind_map = load_industry_map()

    # 行业
    fin["industry_l3"] = fin["code"].map(ind_map)
    fin["industry_l1"] = fin["industry_l3"].map(_l3_to_l1)

    # 添加行情数据（PE/PB/PS/市值）
    pe_data = {}
    pb_data = {}
    ps_data = {}
    close_data = {}
    is_st_data = {}

    for code in fin["code"]:
        pdf = get_price_data(code)
        if pdf is None:
            continue
        t_dt = pd.Timestamp(t_date)
        pdf = pdf[pdf["date"] <= t_dt]
        if pdf.empty:
            continue
        last = pdf.iloc[-1]
        pe_data[code] = last.get("peTTM", np.nan)
        pb_data[code] = last.get("pbMRQ", np.nan)
        ps_data[code] = last.get("psTTM", np.nan)
        close_data[code] = last.get("close", np.nan)
        is_st_data[code] = last.get("isST", 0)

    fin["pe_ttm"] = fin["code"].map(pe_data)
    fin["pb_mrq"] = fin["code"].map(pb_data)
    fin["ps_ttm"] = fin["code"].map(ps_data)
    fin["close"] = fin["code"].map(close_data)
    fin["is_st"] = fin["code"].map(is_st_data).fillna(0).astype(int)

    # 过滤 ST
    fin = fin[fin["is_st"] == 0].copy()

    # 计算衍生指标
    fin["market_cap"] = fin["close"] * fin["total_shares"] / 1e8  # 亿元
    fin["pe_ttm"] = fin["pe_ttm"].replace([np.inf, -np.inf], np.nan)

    # 盈利质量
    fin["profit_margin"] = fin["deducted_profit_q"] / fin["revenue"].replace(0, np.nan)

    # 增长率（直接从TDX字段拿）
    # revenue_yoy, deducted_profit_yoy 已在缓存中

    logger.info(f"Growth数据快照 {t_date}: {len(fin)} 只有效标的")
    return fin


def _l3_to_l1(l3: str) -> str:
    """申万三级 → 一级行业（通过已知的分类规则）。"""
    if not isinstance(l3, str):
        return "未知"
    l1_map = {
        "白酒": "食品饮料", "啤酒": "食品饮料", "乳品": "食品饮料",
        "调味发酵品": "食品饮料", "零食": "食品饮料", "烘焙食品": "食品饮料",
        "半导体设备": "电子", "半导体材料": "电子",
        "集成电路制造": "电子", "集成电路封测": "电子",
        "消费电子零部件及组装": "电子", "品牌消费电子": "电子",
        "LED": "电子", "面板": "电子", "印制电路板": "电子",
        "光伏电池组件": "电力设备", "锂电池": "电力设备",
        "风电整机": "电力设备", "光伏逆变器": "电力设备",
        "航空装备": "国防军工", "军工电子": "国防军工", "航天装备": "国防军工",
        "IT服务": "计算机", "垂直应用软件": "计算机", "横向通用软件": "计算机",
        "化学制剂": "医药生物", "生物制品": "医药生物",
        "医疗设备": "医药生物", "医疗耗材": "医药生物",
        "中药": "医药生物", "医药流通": "医药生物",
        "证券": "非银金融", "保险": "非银金融", "银行": "银行",
        "房地产开发": "房地产", "房地产服务": "房地产",
        "动力煤": "煤炭", "焦煤": "煤炭", "焦炭加工": "煤炭",
        "黄金": "有色金属", "铜": "有色金属", "铝": "有色金属", "锂": "有色金属",
        "炼油化工": "石油石化", "油气开采": "石油石化",
        "氮肥": "基础化工", "磷肥": "基础化工", "农药": "基础化工",
        "工程机械": "机械设备", "机床设备": "机械设备", "机器人": "机械设备",
        "乘用车": "汽车", "商用车": "汽车",
        "汽车电子电气系统": "汽车", "底盘与发动机系统": "汽车",
        "空调": "家用电器", "冰洗": "家用电器", "小家电": "家用电器",
        "生猪养殖": "农林牧渔", "水产养殖": "农林牧渔", "种子": "农林牧渔",
        "火电": "公用事业", "水电": "公用事业", "热电": "公用事业",
        "快递": "交通运输", "航空运输": "交通运输", "航运": "交通运输",
        "电信运营商": "通信", "通信网络设备": "通信", "通信终端及配件": "通信",
    }
    return l1_map.get(l3, "其他")
