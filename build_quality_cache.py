"""构建财务质量缓存 — 从 westock-data zcfz 提取排雷所需字段。

输出: data/cache/quality_snapshot.csv
  columns: code, report_date, goodwill, interest_bear_debt,
           cash_equivalents, equity, inventories, receivables,
           operating_revenue_q
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
CACHE_PATH = "data/cache/quality_snapshot.csv"


def resolve_code(stock_code: str) -> str:
    if stock_code.startswith(("0", "3")):
        return f"sz{stock_code}"
    elif stock_code.startswith("6"):
        return f"sh{stock_code}"
    return f"sz{stock_code}"


def extract_quality_fields(westock_code: str) -> dict | None:
    """从 westock-data finance 提取质量字段。"""
    try:
        result = subprocess.run(
            ["node", WESTOCK_SCRIPT, "finance", westock_code, "--num", "1"],
            capture_output=True, text=True, timeout=60
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    raw = result.stdout

    # 解析 zcfz 表
    zcfz_start = raw.find("**zcfz**")
    zcfz_end = raw.find("**", zcfz_start + 8) if zcfz_start >= 0 else -1
    if zcfz_start < 0:
        return None
    zcfz_section = raw[zcfz_start:zcfz_end] if zcfz_end > zcfz_start else raw[zcfz_start:]

    # 定位表头
    header_match = re.search(r'\|.*EndDate.*GoodWill.*\|', zcfz_section)
    if not header_match:
        return None

    header = header_match.group()
    cols = [c.strip() for c in header.strip("|").split("|")]

    def _col_idx(name):
        try:
            return cols.index(name)
        except ValueError:
            return None

    ed_idx = _col_idx("EndDate")
    gw_idx = _col_idx("GoodWill")
    ibd_idx = _col_idx("InterestBearDebt")
    cash_idx = _col_idx("CashEquivalents")
    eq_idx = _col_idx("SEWithoutMI") or _col_idx("TotalShareholderEquity")
    inv_idx = _col_idx("Inventories")
    recv_idx = _col_idx("ReceivablesFin") or _col_idx("BillAccReceivable")

    if ed_idx is None:
        return None

    # 取第一行数据
    for line in zcfz_section.split("\n"):
        if not line.startswith("|") or "---" in line or "EndDate" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) <= max(filter(None, [ed_idx, gw_idx or 0, ibd_idx or 0])) :
            continue

        def _f(idx):
            if idx is None or idx >= len(cells):
                return None
            try:
                return float(cells[idx])
            except (ValueError, TypeError):
                return None

        return {
            "report_date": cells[ed_idx][:10].replace("-", ""),
            "goodwill": _f(gw_idx),
            "interest_bear_debt": _f(ibd_idx),
            "cash_equivalents": _f(cash_idx),
            "equity": _f(eq_idx),
            "inventories": _f(inv_idx),
            "receivables": _f(recv_idx),
        }

    return None


def build_quality_cache(codes: list[str], force_full: bool = False):
    existing = {}
    if os.path.exists(CACHE_PATH) and not force_full:
        edf = pd.read_csv(CACHE_PATH, dtype={"code": str, "report_date": str})
        for _, row in edf.iterrows():
            existing[(row["code"], row["report_date"])] = row

    records = []
    new_count = 0
    for i, code in enumerate(codes):
        wcode = resolve_code(code)
        fields = extract_quality_fields(wcode)

        if fields:
            key = (code, fields["report_date"])
            if key in existing:
                records.append(existing[key])
            else:
                records.append({"code": code, **fields})
                new_count += 1

        if (i + 1) % 200 == 0:
            logger.info(f"质量缓存进度: {i+1}/{len(codes)}")

    df = pd.DataFrame(records)
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    df.to_csv(CACHE_PATH, index=False)
    logger.info(f"质量缓存: {len(df)} 条, {df['code'].nunique()} 只 ({new_count} 新增)")


if __name__ == "__main__":
    from universe import get_stock_list
    stocks = get_stock_list()
    codes = stocks["code"].tolist()
    force = "--full" in sys.argv
    logger.info(f"开始构建质量缓存: {len(codes)} 只")
    build_quality_cache(codes, force_full=force)
