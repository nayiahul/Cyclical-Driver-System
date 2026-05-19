"""时间完整性治理 — 消除财务数据的前视偏差。

v1.2 升级: 优先使用 westock-data 的实际公告日期 (InfoPublDate)，
          fallback 到法定披露截止日。

A股法定披露截止日 (fallback):
  Q1  (03/31): 当年 4/30
  Q2  (06/30): 当年 8/31
  Q3  (09/30): 当年 10/31
  Q4  (12/31): 次年 4/30
"""
import os
import pandas as pd

_CALENDAR_CACHE = None  # { (code, report_date_str): disclosure_date_str }


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
    """
    calendar = _load_calendar()
    statutory = df["report_date_str"].apply(get_disclosure_cutoff)

    if not calendar:
        return statutory

    # 有日历: 逐行检查 code + report_date_str 是否在日历中
    actual = []
    for _, row in df.iterrows():
        code = row.get("code", "")
        rp = row["report_date_str"]
        key = (str(code), rp)
        if key in calendar:
            actual.append(calendar[key])
        else:
            actual.append(statutory.loc[row.name])
    return pd.Series(actual, index=df.index)


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
