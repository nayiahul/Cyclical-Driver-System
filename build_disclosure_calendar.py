"""构建实际披露日历 — 从 westock-data 获取 InfoPublDate。

用法:
  python build_disclosure_calendar.py           # 增量更新
  python build_disclosure_calendar.py --full    # 全量重建(首次运行)

输出: data/cache/disclosure_calendar.csv
  columns: code, report_date, disclosure_date

disclosure_date = 实际公告日 + 1 交易日(次日开盘可用)
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

WESTOCK_SCRIPT = os.path.expanduser(
    "~/.workbuddy/plugins/marketplaces/cb_teams_marketplace/"
    "plugins/finance-data/skills/westock-data/scripts/index.js"
)
CACHE_PATH = "data/cache/disclosure_calendar.csv"
NUM_PERIODS = 12  # 查询近 12 个报告期


def resolve_code(stock_code: str) -> str:
    """将 6 位代码转换为 westock 格式 (sh/sz + code)。"""
    if stock_code.startswith(("0", "3")):
        return f"sz{stock_code}"
    elif stock_code.startswith("6"):
        return f"sh{stock_code}"
    elif stock_code.startswith(("4", "8", "9")):
        return f"bj{stock_code}"
    return f"sz{stock_code}"


def extract_disclosure_dates(westock_code: str) -> list[tuple[str, str]]:
    """从 westock-data finance 提取 EndDate → InfoPublDate 映射。"""
    try:
        result = subprocess.run(
            ["node", WESTOCK_SCRIPT, "finance", westock_code, "--num", str(NUM_PERIODS)],
            capture_output=True, text=True, timeout=60
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    raw = result.stdout

    # 只解析 lrb 表 (第一个 **lrb** 到下一个 ** 之间)
    lrb_start = raw.find("**lrb**")
    lrb_end = raw.find("**", lrb_start + 7) if lrb_start >= 0 else -1
    if lrb_start < 0:
        return []
    lrb_section = raw[lrb_start:lrb_end] if lrb_end > lrb_start else raw[lrb_start:]

    # 定位 EndDate 和 InfoPublDate 列
    header_match = re.search(r'\|.*EndDate.*InfoPublDate.*\|', lrb_section)
    if not header_match:
        return []

    header = header_match.group()
    cols = [c.strip() for c in header.strip("|").split("|")]
    try:
        ed_idx = cols.index("EndDate")
        ip_idx = cols.index("InfoPublDate")
    except ValueError:
        return []

    dates = []
    for line in lrb_section.split("\n"):
        if not line.startswith("|") or "---" in line or "EndDate" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) <= max(ed_idx, ip_idx):
            continue
        ed = cells[ed_idx][:10]
        ip = cells[ip_idx][:10]
        # 验证日期格式 YYYY-MM-DD
        if re.match(r'\d{4}-\d{2}-\d{2}', ed) and re.match(r'\d{4}-\d{2}-\d{2}', ip):
            # 转换为 YYYYMMDD
            ed_compact = ed.replace("-", "")
            ip_compact = ip.replace("-", "")
            dates.append((ed_compact, ip_compact))

    return dates


def build_calendar(codes: list[str], force_full: bool = False):
    """构建全量披露日历。"""
    existing = {}
    if os.path.exists(CACHE_PATH) and not force_full:
        edf = pd.read_csv(CACHE_PATH, dtype={"code": str, "report_date": str, "disclosure_date": str})
        for _, row in edf.iterrows():
            existing[(row["code"], row["report_date"])] = row["disclosure_date"]

    records = []
    new_count = 0
    for i, code in enumerate(codes):
        wcode = resolve_code(code)
        dates = extract_disclosure_dates(wcode)

        for rp, dd in dates:
            key = (code, rp)
            if key in existing:
                records.append({"code": code, "report_date": rp, "disclosure_date": existing[key]})
            else:
                records.append({"code": code, "report_date": rp, "disclosure_date": dd})
                new_count += 1

        if (i + 1) % 200 == 0:
            logger.info(f"披露日历进度: {i+1}/{len(codes)}")

    df = pd.DataFrame(records)
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    df.to_csv(CACHE_PATH, index=False)

    n_codes = df["code"].nunique()
    n_periods = df["report_date"].nunique()
    logger.info(f"披露日历: {len(df)} 条, {n_codes} 只股票, {n_periods} 个报告期 ({new_count} 条新增)")


def load_calendar() -> pd.DataFrame:
    """加载披露日历缓存。"""
    if os.path.exists(CACHE_PATH):
        return pd.read_csv(CACHE_PATH, dtype={"code": str, "report_date": str, "disclosure_date": str})
    return pd.DataFrame(columns=["code", "report_date", "disclosure_date"])


if __name__ == "__main__":
    from universe import get_stock_list
    stocks = get_stock_list()
    codes = stocks["code"].tolist()
    force = "--full" in sys.argv
    logger.info(f"开始构建披露日历: {len(codes)} 只股票")
    build_calendar(codes, force_full=force)
