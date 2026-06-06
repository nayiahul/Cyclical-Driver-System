"""财报披露周期感知 — 季报密集期 vs 业绩真空期"""
from datetime import datetime
from config.params import DISCLOSURE_MONTHS


def is_disclosure_season(t_date: str = None) -> bool:
    """判断当前是否在财报密集披露期。

    Args:
        t_date: 日期字符串 YYYYMMDD，默认今天

    Returns:
        True if month in DISCLOSURE_MONTHS
    """
    if t_date is None:
        t_date = datetime.now().strftime("%Y%m%d")
    month = int(t_date[4:6])
    return month in DISCLOSURE_MONTHS


def get_season_label(t_date: str = None) -> str:
    """返回季节标签。

    Returns:
        "DISCLOSURE" | "VACUUM"
    """
    return "DISCLOSURE" if is_disclosure_season(t_date) else "VACUUM"
