"""PDF数据集成层 — 缓存 + 注入 Growth OS 打分引擎。

将 PDF 提取的结构化数据缓存在 data/cache/pdf_financials.csv，
供 funnel.py 读取使用。
"""
import json
import os
from pathlib import Path
from typing import Optional
from loguru import logger

import pandas as pd

from growth_os.pdf_download import get_latest_report_path, PDF_ROOT
from growth_os.pdf_extract import (
    extract_inventory_breakdown,
    extract_rd_capitalization,
    extract_subsidy_detail,
    extract_segment_revenue,
    extract_ar_aging,
)

PDF_CACHE_PATH = "data/cache/pdf_financials.csv"


# ============================================================
# 缓存层
# ============================================================

def _load_cache() -> pd.DataFrame:
    """加载 PDF 数据缓存。"""
    if os.path.exists(PDF_CACHE_PATH):
        return pd.read_csv(PDF_CACHE_PATH, dtype={"code": str})
    return pd.DataFrame(columns=["code", "report_year", "category"])


def _save_cache(df: pd.DataFrame):
    """保存 PDF 数据缓存。"""
    os.makedirs(os.path.dirname(PDF_CACHE_PATH), exist_ok=True)
    df.to_csv(PDF_CACHE_PATH, index=False, encoding="utf-8-sig")


def get_cached_pdf_data(code: str, year: int = None) -> dict | None:
    """从缓存读取某只股票的 PDF 数据。"""
    cache = _load_cache()
    if cache.empty:
        return None
    mask = cache["code"] == code
    if year:
        mask &= cache["report_year"] == year
    rows = cache[mask]
    if rows.empty:
        return None
    # 取最新
    row = rows.sort_values("report_year").iloc[-1]
    return row.to_dict()


# ============================================================
# 提取 + 缓存
# ============================================================

def extract_and_cache(code: str, force: bool = False) -> dict:
    """提取单只股票的 PDF 数据，写入缓存。

    Returns:
        {"inventory_raw_materials": ..., "rd_capitalization_rate": ...,
         "subsidy_amount": ..., "ar_within_1y_pct": ..., "segments": ...}
    """
    # 检查缓存
    if not force:
        cached = get_cached_pdf_data(code)
        if cached:
            return cached

    result = {"code": code, "report_year": None, "category": "annual"}

    # 获取最新年报
    pdf_path = get_latest_report_path(code, "annual")
    if not pdf_path:
        logger.debug(f"{code}: 无年报PDF")
        return result

    result["report_year"] = _extract_year_from_filename(pdf_path.name)
    logger.info(f"提取 {code} PDF: {pdf_path.name}")

    # 1. 存货结构
    inv = extract_inventory_breakdown(pdf_path)
    if inv:
        result["inv_raw_materials"] = inv.get("raw_materials")
        result["inv_work_in_progress"] = inv.get("work_in_progress")
        result["inv_finished_goods"] = inv.get("finished_goods")
        # 产成品占比 = 产成品/存货总额
        if inv.get("total") and inv.get("finished_goods"):
            result["inv_finished_pct"] = round(
                inv["finished_goods"] / inv["total"] * 100, 1)

    # 2. 研发资本化率
    rd = extract_rd_capitalization(pdf_path)
    if rd:
        result["rd_capitalization_rate"] = rd.get("capitalization_rate")
        result["rd_expense_total"] = rd.get("rd_expense_total")

    # 3. 政府补助
    subsidy = extract_subsidy_detail(pdf_path)
    if subsidy:
        result["subsidy_amount"] = subsidy.get("current_subsidy")

    # 4. 分部报告（存 JSON）
    segments = extract_segment_revenue(pdf_path)
    if segments:
        result["segments_json"] = json.dumps(segments, ensure_ascii=False)
        # 高毛利业务占比
        if len(segments) >= 2:
            high_gm_segs = [s for s in segments
                            if s.get("gross_margin", 0) > 40]
            total_rev = sum(s.get("revenue", 0) for s in segments
                            if s.get("revenue"))
            if total_rev > 0 and high_gm_segs:
                high_gm_rev = sum(s["revenue"] for s in high_gm_segs
                                  if s.get("revenue"))
                result["high_gm_segment_pct"] = round(
                    high_gm_rev / total_rev * 100, 1)

    # 5. 应收账款账龄
    ar_aging = extract_ar_aging(pdf_path)
    if ar_aging:
        result["ar_within_1y_pct"] = ar_aging.get("within_1y_pct")
        result["ar_over_3y_pct"] = round(
            100 - ar_aging.get("within_1y_pct", 100), 1) \
            if ar_aging.get("within_1y_pct") else None

    # 6. 客户集中度
    from growth_os.pdf_extract import extract_customer_concentration
    cust = extract_customer_concentration(pdf_path)
    if cust:
        result["top5_customer_ratio"] = cust.get("top5_ratio")
        result["top1_customer_ratio"] = cust.get("top1_ratio")

    # 写入缓存
    cache = _load_cache()
    # 删除旧记录
    cache = cache[~((cache["code"] == code) &
                    (cache["report_year"] == result["report_year"]))]
    new_row = pd.DataFrame([result])
    cache = pd.concat([cache, new_row], ignore_index=True)
    _save_cache(cache)

    return result


# ============================================================
# 批量处理
# ============================================================

def build_pdf_cache(codes: list[str], force: bool = False):
    """批量提取 PDF 数据，写入缓存。

    建议先下载PDF再提取。
    """
    from growth_os.pdf_download import download_reports_batch

    total = len(codes)
    for i, code in enumerate(codes):
        if (i + 1) % 50 == 0:
            logger.info(f"PDF进度: {i + 1}/{total}")

        # 检查是否已有缓存
        if not force and get_cached_pdf_data(code):
            continue

        # 先下载再提取
        pdfs = download_reports_batch(code)
        if pdfs:
            extract_and_cache(code, force=True)


# ============================================================
# 打分引擎集成接口
# ============================================================

def get_inventory_signal(code: str) -> dict:
    """获取存货结构信号，供 L1 排雷使用。

    Returns:
        {"finished_pct": 产成品占比, "warning": 是否预警,
         "detail": 说明}

    产成品占比>60% → 滞销风险（黄色预警）
    原材料+在产品占比>60% → 主动备产（正面信号）
    """
    data = get_cached_pdf_data(code)
    if not data:
        return {"finished_pct": None, "warning": False, "detail": "无PDF数据"}

    finished_pct = data.get("inv_finished_pct")
    raw_pct = None
    if data.get("inv_raw_materials") and data.get("inv_total"):
        raw_pct = data["inv_raw_materials"] / data.get("inv_total", 1) * 100 \
            if data.get("inv_total") else None

    if finished_pct is None:
        return {"finished_pct": None, "warning": False, "detail": "存货结构未提取到"}

    if finished_pct > 60:
        return {
            "finished_pct": finished_pct,
            "warning": True,
            "severity": "yellow",
            "detail": f"产成品占比{finished_pct:.0f}%，存在滞销风险",
        }
    elif finished_pct < 30:
        return {
            "finished_pct": finished_pct,
            "raw_pct": raw_pct,
            "warning": False,
            "detail": f"产成品占比{finished_pct:.0f}%，存货结构健康（主动备产型）",
        }
    else:
        return {
            "finished_pct": finished_pct,
            "warning": False,
            "detail": f"产成品占比{finished_pct:.0f}%，正常范围",
        }


def get_rd_quality_signal(code: str) -> dict:
    """获取研发质量信号，供 L2 护城河使用。

    Returns:
        {"capitalization_rate": 资本化率, "warning": True if >30%,
         "detail": 说明}

    资本化率>30% → 虚增利润嫌疑（红色预警）
    """
    data = get_cached_pdf_data(code)
    if not data:
        return {"capitalization_rate": None, "warning": False, "detail": "无PDF数据"}

    cap_rate = data.get("rd_capitalization_rate")
    if cap_rate is None:
        return {"capitalization_rate": None, "warning": False, "detail": "未提取到"}

    if cap_rate > 50:
        return {"capitalization_rate": cap_rate, "warning": True,
                "severity": "red",
                "detail": f"研发资本化率{cap_rate:.0f}%，严重虚增利润嫌疑"}
    elif cap_rate > 30:
        return {"capitalization_rate": cap_rate, "warning": True,
                "severity": "yellow",
                "detail": f"研发资本化率{cap_rate:.0f}%，偏高需关注"}
    else:
        return {"capitalization_rate": cap_rate, "warning": False,
                "detail": f"研发资本化率{cap_rate:.0f}%，正常"}


def get_subsidy_signal(code: str, deducted_profit: float = None) -> dict:
    """获取政府补助依赖信号。

    Returns:
        {"subsidy_to_profit": 补助/扣非利润比, "warning": True if >50%}
    """
    data = get_cached_pdf_data(code)
    if not data:
        return {"subsidy_to_profit": None, "warning": False, "detail": "无PDF数据"}

    subsidy = data.get("subsidy_amount")
    if subsidy is None:
        return {"subsidy_to_profit": None, "warning": False, "detail": "未提取到"}

    if deducted_profit and deducted_profit > 0:
        ratio = subsidy / deducted_profit * 100
        if ratio > 50:
            return {"subsidy_to_profit": round(ratio, 1), "warning": True,
                    "severity": "red",
                    "detail": f"政府补助占扣非利润{ratio:.0f}%，严重依赖"}
        elif ratio > 20:
            return {"subsidy_to_profit": round(ratio, 1), "warning": True,
                    "severity": "yellow",
                    "detail": f"政府补助占扣非利润{ratio:.0f}%，偏高"}
        else:
            return {"subsidy_to_profit": round(ratio, 1), "warning": False,
                    "detail": f"政府补助占扣非利润{ratio:.0f}%，正常"}

    return {"subsidy_to_profit": None, "warning": False,
            "detail": f"补助金额: {subsidy/1e8:.1f}亿"}


def _extract_year_from_filename(fname: str) -> int:
    """从文件名中提取年份，如 '600519_2024年_年度报告.pdf'。"""
    match = re.search(r"(\d{4})", fname)
    return int(match.group(1)) if match else 0


import re
