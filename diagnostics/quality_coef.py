"""三大前提质量系数 — 移植自 pailou.py 的唐朝方法论。

返回 0.7-1.0 的调整系数，乘以 composite 做软降权。

前提1: 利润为真 — OCF/NP≥1 的期数占比
前提2: 利润可持续 — 毛利率趋势稳定
前提3: 无需再投入 — FCFF/NP 比率

数据源: westock-data finance (lrb + xjll)
"""
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

WESTOCK_SCRIPT = os.path.expanduser(
    "~/.workbuddy/plugins/marketplaces/cb_teams_marketplace/"
    "plugins/finance-data/skills/westock-data/scripts/index.js"
)


def resolve_code(stock_code: str) -> str:
    if stock_code.startswith(("sh", "sz", "bj", "hk")):
        return stock_code  # 已有前缀
    if stock_code.startswith(("0", "3")):
        return f"sz{stock_code}"
    elif stock_code.startswith("6"):
        return f"sh{stock_code}"
    return f"sz{stock_code}"


def fetch_three_premises(stock_code: str, num_periods: int = 8) -> dict | None:
    """从 westock-data 获取财务数据，计算三大前提得分。

    Returns:
        {"profit_real": 0.8-1.0, "profit_sustainable": 0.8-1.0,
         "low_reinvestment": 0.8-1.0, "overall": 0.5-1.0}
        or None if data unavailable
    """
    wcode = resolve_code(stock_code)
    try:
        result = subprocess.run(
            ["node", WESTOCK_SCRIPT, "finance", wcode, "--num", str(num_periods)],
            capture_output=True, text=True, timeout=60
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    raw = result.stdout

    # 解析 lrb
    lrb_data = _parse_table(raw, "lrb")
    xjll_data = _parse_table(raw, "xjll")

    if not lrb_data or not xjll_data:
        return None

    # 前提1: 利润为真
    p1 = _check_profit_real(lrb_data, xjll_data)

    # 前提2: 利润可持续
    p2 = _check_profit_sustainable(lrb_data)

    # 前提3: 无需大量再投入
    p3 = _check_low_reinvestment(xjll_data)

    if p1 is None and p2 is None and p3 is None:
        return None

    overall = 1.0
    for p in [p1, p2, p3]:
        if p is not None:
            overall *= p

    return {
        "profit_real": p1 or 1.0,
        "profit_sustainable": p2 or 1.0,
        "low_reinvestment": p3 or 1.0,
        "overall": round(overall, 3),
    }


def _parse_table(raw: str, table_name: str) -> list[dict] | None:
    """解析 westock-data markdown 表格。"""
    start = raw.find(f"**{table_name}**")
    if start < 0:
        return None
    # 找下一个 ** 标记作为结束
    rest = raw[start + len(table_name) + 4:]
    end_marker = rest.find("\n**")
    section = rest[:end_marker] if end_marker > 0 else rest

    # 找表头行 (第一行以 | 开头且不含 ---)
    lines = section.strip().split("\n")
    header_line = None
    data_start = 0
    for i, line in enumerate(lines):
        if line.startswith("|") and "---" not in line:
            header_line = line
            data_start = i + 2  # 跳过表头和分隔符行
            break

    if not header_line:
        return None

    headers = [h.strip() for h in header_line.strip("|").split("|")]
    rows = []
    for line in lines[data_start:]:
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < len(headers):
            continue
        row = {}
        for i, h in enumerate(headers):
            if i < len(cells):
                try:
                    row[h] = float(cells[i])
                except (ValueError, TypeError):
                    row[h] = cells[i]
        rows.append(row)

    return rows if rows else None


def _check_profit_real(lrb: list[dict], xjll: list[dict]) -> float | None:
    """前提1: OCF_Q / NP_Q ≥ 1 的期数占比 (单季度对比, 避免累计口径混用)"""
    np_key = next((k for k in lrb[0] if "NPParentCompanyOwners_Q" in k), None)
    ocf_key = next((k for k in xjll[0] if "NetOperateCashFlow_Q" in k), None)

    if not np_key or not ocf_key:
        return None

    # 按日期对齐
    lrb_by_date = {}
    for r in lrb:
        d = str(r.get("EndDate", r.get("_date", "")))[:10]
        if d:
            lrb_by_date[d] = r

    pass_count = 0
    total = 0
    for r in xjll:
        d = str(r.get("EndDate", r.get("_date", "")))[:10]
        if d in lrb_by_date:
            np_v = lrb_by_date[d].get(np_key)
            ocf_v = r.get(ocf_key)
            if np_v and ocf_v and np_v > 0:
                total += 1
                if ocf_v / np_v >= 1.0:
                    pass_count += 1

    if total < 4:
        return None
    ratio = pass_count / total
    if ratio >= 0.75: return 1.0
    elif ratio >= 0.50: return 0.9
    else: return 0.8


def _check_profit_sustainable(lrb: list[dict]) -> float | None:
    """前提2: 毛利率(TTM)趋势。降幅<5pp → 1.0, 5-15pp → 0.9, >15pp → 0.8"""
    gp_key = next((k for k in lrb[0] if "GrossProfitTTM" in k), None)
    rev_key = next((k for k in lrb[0] if "OperatingRevenueTTM" in k), None)
    if not gp_key or not rev_key:
        return None

    latest_gp = lrb[0].get(gp_key)
    latest_rev = lrb[0].get(rev_key)
    oldest_gp = lrb[-1].get(gp_key)
    oldest_rev = lrb[-1].get(rev_key)
    if not all([latest_gp, latest_rev, oldest_gp, oldest_rev]):
        return None
    if latest_rev <= 0 or oldest_rev <= 0:
        return None

    latest_gm = latest_gp / latest_rev
    oldest_gm = oldest_gp / oldest_rev
    change_pp = (latest_gm - oldest_gm) * 100
    if change_pp > -5: return 1.0
    elif change_pp > -15: return 0.9
    else: return 0.8


def _check_low_reinvestment(xjll: list[dict]) -> float | None:
    """前提3: FCFF均值 / NP均值 > 0.5 → 1.0, 0-0.5 → 0.9, <0 → 0.8"""
    fcff_key = next((k for k in xjll[0] if k == "FCFF"), None)
    np_key = next((k for k in xjll[0] if "NPDeductNonRecurringPL_Q" in k), None)
    if not fcff_key or not np_key:
        return None

    fcff_vals = [r[fcff_key] for r in xjll if isinstance(r.get(fcff_key), (int, float)) and not pd.isna(r.get(fcff_key))]
    np_vals = [r[np_key] for r in xjll if isinstance(r.get(np_key), (int, float)) and not pd.isna(r.get(np_key))]
    if not fcff_vals or not np_vals:
        return None

    avg_fcff = np.mean(fcff_vals)
    avg_np = np.mean(np_vals)
    if avg_np <= 0: return 0.8
    ratio = avg_fcff / avg_np
    if ratio > 0.5: return 1.0
    elif ratio > 0: return 0.9
    else: return 0.8


if __name__ == "__main__":
    # 测试
    for code in ["sh600519", "sz000858", "sz002466"]:
        result = fetch_three_premises(code)
        print(f"{code}: {result}")
