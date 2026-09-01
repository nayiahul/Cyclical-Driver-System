"""时间完整性治理 — 消除财务数据的前视偏差。

v1.2 升级: 优先使用 westock-data 的实际公告日期 (InfoPublDate)，
          fallback 到法定披露截止日。

A股法定披露截止日 (fallback):
  Q1  (03/31): 当年 4/30
  Q2  (06/30): 当年 8/31
  Q3  (09/30): 当年 10/31
  Q4  (12/31): 次年 4/30

v1.3 (Gate 0-A 性能优化, 无语义变更):
  - _compute_cutoff_map 向量化 (iterrows → np.select + flat dict map)
  - 新增 load_tdx_raw() 共享加载，消除每调仓日 4 次重复读 283MB 缓存
"""
import os
import numpy as np
import pandas as pd

_CALENDAR_CACHE = None  # { (code, report_date_str): disclosure_date_str }
_TDX_RAW_CACHE = None  # TDX 财务缓存 DataFrame（进程内只读一次）


def load_tdx_raw():
    """加载 TDX 财务缓存（模块级缓存，进程内只读一次）。

    文件不存在时返回 None，与调用方原有的 os.path.exists 守卫语义一致。
    """
    global _TDX_RAW_CACHE
    if _TDX_RAW_CACHE is not None:
        return _TDX_RAW_CACHE
    path = "data/cache/tdx_financials.csv"
    if not os.path.exists(path):
        return None
    _TDX_RAW_CACHE = pd.read_csv(path, dtype={"code": str, "report_date_str": str})
    return _TDX_RAW_CACHE


def _load_calendar():
    """延迟加载披露日历。"""
    global _CALENDAR_CACHE
    if _CALENDAR_CACHE is not None:
        return _CALENDAR_CACHE
    path = "data/cache/disclosure_calendar.csv"
    if os.path.exists(path):
        df = pd.read_csv(path, dtype={"code": str, "report_date": str, "disclosure_date": str})
        _CALENDAR_CACHE = {}
        for _, row in df.iterrows():
            _CALENDAR_CACHE[(row["code"], row["report_date"])] = row["disclosure_date"]
    else:
        _CALENDAR_CACHE = {}
    return _CALENDAR_CACHE


def get_disclosure_cutoff(report_period: str) -> str:
    """法定披露截止日 (YYYYMMDD)。"""
    year = int(report_period[:4])
    month_day = report_period[4:]
    if month_day == "0331":
        return f"{year}0430"
    elif month_day == "0630":
        return f"{year}0831"
    elif month_day == "0930":
        return f"{year}1031"
    elif month_day == "1231":
        return f"{year + 1}0430"
    else:
        return report_period


def get_disclosure_cutoff_dash(report_period: str) -> str:
    """同 get_disclosure_cutoff，但输入/输出均为 YYYY-MM-DD 格式。"""
    compact = report_period.replace("-", "")
    result_compact = get_disclosure_cutoff(compact)
    return f"{result_compact[:4]}-{result_compact[4:6]}-{result_compact[6:8]}"


def _compute_cutoff_map(df, t_date: str) -> pd.Series:
    """为 DataFrame 每一行计算最早可用日期 (YYYYMMDD)。

    优先使用实际披露日历，fallback 到法定截止日。
    v1.3: 向量化实现，输出与 v1.2 逐位一致（同一 key 同一结果）。
    """
    calendar = _load_calendar()
    rp = df["report_date_str"]

    # 法定截止日向量化: 0331→0430 / 0630→0831 / 0930→1031 / 1231→次年0430
    year = rp.str[:4].astype(int)
    md = rp.str[4:]
    statutory = np.select(
        [md == "0331", md == "0630", md == "0930", md == "1231"],
        [year * 10000 + 430, year * 10000 + 831,
         year * 10000 + 1031, (year + 1) * 10000 + 430],
        default=rp,
    ).astype(str)

    if not calendar:
        return pd.Series(statutory, index=df.index)

    # 实际披露日 lookup（向量化）: flat dict {code+report_date: disclosure}
    flat = {f"{c}{rp_}": d for (c, rp_), d in calendar.items()}
    keys = (df["code"].astype(str) + rp).tolist()
    actual = pd.Series(keys).map(flat)
    out = actual.where(actual.notna(), pd.Series(statutory, index=range(len(df)))).tolist()
    return pd.Series(out, index=df.index)


def filter_available_reports(df, t_date: str):
    """过滤 DataFrame，仅保留截至 t_date 已过披露截止日的报告期数据。

    优先使用实际披露日历 (westock-data InfoPublDate)，
    fallback 到法定截止日。
    """
    if df.empty:
        return df.copy()
    cutoffs = _compute_cutoff_map(df, t_date)
    return df[cutoffs <= t_date].copy()


def filter_available_reports_dash(df, date_col: str, t_date: str):
    """同 filter_available_reports，但 date_col 使用 YYYY-MM-DD 格式。

    用于 AKShare 财务数据 (financial_data.csv)。
    注意: AKShare 数据无实际披露日历，始终使用法定截止日。
    """
    t_date_dash = f"{t_date[:4]}-{t_date[4:6]}-{t_date[6:8]}"
    cutoffs = df[date_col].astype(str).apply(get_disclosure_cutoff_dash)
    return df[cutoffs <= t_date_dash].copy()
