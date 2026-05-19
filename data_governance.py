"""时间完整性治理 — 消除财务数据的前视偏差。

v1.0 基础设施审计核心模块。
A股法定披露截止日:
  Q1  (03/31): 当年 4/30
  Q2  (06/30): 当年 8/31
  Q3  (09/30): 当年 10/31
  Q4  (12/31): 次年 4/30

在选股日 t_date，仅当 t_date >= 法定截止日时，该报告期数据才可被系统"看见"。
"""


def get_disclosure_cutoff(report_period: str) -> str:
    """返回报期内财务数据的最早可用日期 (YYYYMMDD)。

    Args:
        report_period: 报告期字符串，如 "20251231"

    Returns:
        法定披露截止日，如 "20260430"
    """
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
    """同 get_disclosure_cutoff，但输入/输出均为 YYYY-MM-DD 格式。

    用于 AKShare 财务数据 (financial_data.csv)。
    """
    compact = report_period.replace("-", "")
    result_compact = get_disclosure_cutoff(compact)
    return f"{result_compact[:4]}-{result_compact[4:6]}-{result_compact[6:8]}"


def filter_available_reports(df, t_date: str):
    """过滤 DataFrame，仅保留截至 t_date 已过披露截止日的报告期数据。

    Args:
        df: 含 report_date_str 列的 DataFrame (YYYYMMDD 格式)
        t_date: 选股日 YYYYMMDD

    Returns:
        过滤后的 DataFrame (copy)
    """
    cutoffs = df["report_date_str"].apply(get_disclosure_cutoff)
    return df[cutoffs <= t_date].copy()


def filter_available_reports_dash(df, date_col: str, t_date: str):
    """同 filter_available_reports，但 date_col 使用 YYYY-MM-DD 格式。

    用于 AKShare 财务数据 (financial_data.csv)。

    Args:
        df: 含 date_col 列的 DataFrame (YYYY-MM-DD 格式)
        date_col: 日期列名，如 "date"
        t_date: 选股日 YYYYMMDD

    Returns:
        过滤后的 DataFrame (copy)
    """
    cutoffs = df[date_col].astype(str).apply(get_disclosure_cutoff_dash)
    t_date_dash = f"{t_date[:4]}-{t_date[4:6]}-{t_date[6:8]}"
    return df[cutoffs <= t_date_dash].copy()
