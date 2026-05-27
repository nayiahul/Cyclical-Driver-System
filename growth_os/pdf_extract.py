"""财报PDF附录提取 — 存货结构/研发资本化/政府补助/分部报告/应收账龄。

依赖: camelot-py (lattice模式) + pdfplumber (text模式)
安装: pip install camelot-py pdfplumber opencv-python ghostscript
"""
import re, os
from pathlib import Path
from typing import Optional
from loguru import logger

import pandas as pd
import numpy as np

try:
    import pdfplumber
except ImportError:
    pdfplumber = None
    logger.warning("pdfplumber 未安装，仅文本表格提取不可用")

try:
    import camelot
except ImportError:
    camelot = None
    logger.warning("camelot 未安装，结构化表格提取不可用")


# ============================================================
# 1. 通用表格提取
# ============================================================

def extract_tables(pdf_path: str | Path, pages: str = "all",
                   method: str = "auto") -> list[pd.DataFrame]:
    """从PDF提取所有表格。

    Args:
        pdf_path: PDF 文件路径
        pages: 页码范围，如 "200-220" 或 "all"
        method: "camelot" | "pdfplumber" | "auto"

    Returns:
        DataFrame 列表
    """
    tables = []

    # 方式1: camelot lattice (有边框表格)
    if method in ("camelot", "auto") and camelot:
        try:
            if pages == "all":
                camelot_tables = camelot.read_pdf(str(pdf_path), pages="1-end",
                                                  flavor="lattice")
            else:
                camelot_tables = camelot.read_pdf(str(pdf_path), pages=pages,
                                                  flavor="lattice")
            for t in camelot_tables:
                df = t.df
                if len(df) > 1:
                    tables.append(df)
            if tables:
                return _clean_tables(tables)
        except Exception as e:
            logger.debug(f"camelot lattice 失败: {e}")

    # 方式2: pdfplumber (无边框文本表格)
    if method in ("pdfplumber", "auto") and pdfplumber:
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                if pages == "all":
                    page_range = pdf.pages
                else:
                    parts = pages.split("-")
                    start = int(parts[0]) - 1
                    end = int(parts[1]) - 1 if len(parts) > 1 else start
                    page_range = pdf.pages[start:end + 1]

                for page in page_range:
                    page_tables = page.extract_tables()
                    for pt in page_tables:
                        if pt and len(pt) > 1:
                            df = pd.DataFrame(pt[1:], columns=pt[0])
                            tables.append(df)
        except Exception as e:
            logger.debug(f"pdfplumber 失败: {e}")

    return _clean_tables(tables)


def _clean_tables(tables: list[pd.DataFrame]) -> list[pd.DataFrame]:
    """清理提取的表格：用第一行做列名、删除空列/行。"""
    cleaned = []
    for df in tables:
        # 第一行做列名
        if isinstance(df.iloc[0, 0], str) and not any(
                str(c).replace(".", "").replace("%", "").isdigit()
                for c in df.iloc[0] if c):
            df.columns = df.iloc[0]
            df = df.iloc[1:]

        # 去完全空的行和列
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if len(df) > 1:
            cleaned.append(df.reset_index(drop=True))
    return cleaned


# ============================================================
# 2. 存货结构提取
# ============================================================

def extract_inventory_breakdown(pdf_path: str | Path) -> dict | None:
    """提取存货结构：原材料、在产品、产成品金额。

    搜索关键词: "存货分类"、"存货构成"、"存货明细"
    通常出现在年报附注"存货"章节。

    Returns:
        {"raw_materials": 金额, "work_in_progress": 金额,
         "finished_goods": 金额, "total": 金额, "source_page": 页码}
    """
    tables = extract_tables(pdf_path, pages="all", method="auto")
    if not tables:
        return None

    inv_keywords = ["原材料", "在产品", "库存商品", "产成品", "发出商品", "委托加工"]
    for df in tables:
        # 检查是否包含存货关键词
        text_flat = " ".join(df.astype(str).values.flatten()).lower()
        if not any(kw in text_flat for kw in inv_keywords[:3]):
            continue

        # 尝试找到数值列
        result = {"raw_materials": None, "work_in_progress": None,
                  "finished_goods": None, "total": None}

        for _, row in df.iterrows():
            row_str = " ".join(str(v) for v in row.values)
            vals = _extract_numeric_values(row)

            if any(kw in row_str for kw in ["原材料", "原料"]):
                result["raw_materials"] = _pick_best_value(vals)
            elif any(kw in row_str for kw in ["在产品", "半成品"]):
                result["work_in_progress"] = _pick_best_value(vals)
            elif any(kw in row_str for kw in ["库存商品", "产成品"]):
                result["finished_goods"] = _pick_best_value(vals)
            elif any(kw in row_str for kw in ["合计", "账面价值", "账面余额"]):
                result["total"] = _pick_best_value(vals)

        # 至少要有两项才认为有效
        valid_count = sum(1 for v in result.values() if v is not None)
        if valid_count >= 2:
            return result

    return None


# ============================================================
# 3. 研发资本化率
# ============================================================

def extract_rd_capitalization(pdf_path: str | Path) -> dict | None:
    """提取研发资本化率。

    搜索关键词: "研发投入"、"研发支出"、"开发支出"
    Returns:
        {"rd_expense_total": 总研发支出, "rd_capitalized": 资本化金额,
         "rd_expensed": 费用化金额, "capitalization_rate": 资本化率%}
    """
    tables = extract_tables(pdf_path, pages="all", method="auto")

    rd_keywords = ["研发投入", "研发支出", "资本化", "费用化", "开发支出"]
    for df in tables:
        text_flat = " ".join(df.astype(str).values.flatten())
        if not any(kw in text_flat for kw in rd_keywords[:2]):
            continue

        result = {}
        for _, row in df.iterrows():
            row_str = " ".join(str(v) for v in row.values)
            vals = _extract_numeric_values(row)

            if "资本化" in row_str and "研发" in row_str:
                result["rd_capitalized"] = _pick_best_value(vals)
            elif "费用化" in row_str and "研发" in row_str:
                result["rd_expensed"] = _pick_best_value(vals)
            elif "合计" in row_str and any(kw in text_flat for kw in ["研发", "开发"]):
                result["rd_expense_total"] = _pick_best_value(vals)

        if result.get("rd_capitalized") and result.get("rd_expensed"):
            total = result.get("rd_expense_total") or (
                result["rd_capitalized"] + result["rd_expensed"])
            result["rd_expense_total"] = total
            result["capitalization_rate"] = round(
                result["rd_capitalized"] / total * 100, 1)
            return result

    return None


# ============================================================
# 4. 政府补助明细
# ============================================================

def extract_subsidy_detail(pdf_path: str | Path) -> dict | None:
    """提取政府补助金额。

    搜索关键词: "政府补助"、"补贴收入"、"递延收益"
    Returns:
        {"current_subsidy": 当期补助, "deferred_subsidy": 递延收益,
         "subsidy_to_profit_ratio": 补助/利润比(%)}
    """
    tables = extract_tables(pdf_path, pages="all", method="auto")

    for df in tables:
        text_flat = " ".join(df.astype(str).values.flatten())
        if "政府补助" not in text_flat and "计入当期" not in text_flat:
            continue

        result = {}
        for _, row in df.iterrows():
            row_str = " ".join(str(v) for v in row.values)
            vals = _extract_numeric_values(row)

            if any(kw in row_str for kw in ["计入当期损益", "当期损益", "计入当期"]):
                result["current_subsidy"] = _pick_best_value(vals)
            elif any(kw in row_str for kw in ["递延收益", "尚未摊销"]):
                result["deferred_subsidy"] = _pick_best_value(vals)
            elif ("合计" in row_str or "总计" in row_str):
                if "current_subsidy" not in result:
                    result["current_subsidy"] = _pick_best_value(vals)

        if result.get("current_subsidy"):
            return result

    return None


# ============================================================
# 5. 分部报告（分行业/分产品）
# ============================================================

def extract_segment_revenue(pdf_path: str | Path) -> list[dict] | None:
    """提取分部收入（分行业或分产品）。

    搜索关键词: "分行业"、"分产品"、"主营业务分"
    Returns:
        [{segment_name, revenue, cost, gross_margin(%)}]
    """
    tables = extract_tables(pdf_path, pages="all", method="auto")

    segment_keywords = ["分行业", "分产品", "主营业务分", "营业收入构成"]
    for df in tables:
        text_flat = " ".join(df.astype(str).values.flatten())
        if not any(kw in text_flat for kw in segment_keywords):
            continue

        segments = []
        for _, row in df.iterrows():
            row_str = " ".join(str(v) for v in row.values)
            vals = _extract_numeric_values(row)

            # 跳过表头/合计行
            if any(kw in row_str for kw in ["合计", "总计", "项目", "行业"]):
                continue
            if not vals:
                continue

            seg_name = str(row.values[0]) if len(row.values) > 0 else ""
            if seg_name and len(vals) >= 1:
                seg = {"name": seg_name.strip(), "revenue": vals[0] if vals else None}
                if len(vals) >= 2:
                    seg["cost"] = vals[1]
                    if seg["revenue"] and seg["revenue"] > 0:
                        seg["gross_margin"] = round(
                            (1 - seg["cost"] / seg["revenue"]) * 100, 1)
                segments.append(seg)

        if len(segments) >= 2:
            return segments

    return None


# ============================================================
# 6. 应收账款账龄
# ============================================================

def extract_ar_aging(pdf_path: str | Path) -> dict | None:
    """提取应收账款账龄结构。

    Returns:
        {"within_1y": 1年内, "1_to_2y": 1-2年, "2_to_3y": 2-3年,
         "over_3y": 3年以上, "total": 合计, "within_1y_pct": 1年内占比%}
    """
    tables = extract_tables(pdf_path, pages="all", method="auto")

    for df in tables:
        text_flat = " ".join(df.astype(str).values.flatten())
        if "账龄" not in text_flat or "应收" not in text_flat:
            continue

        result = {}
        for _, row in df.iterrows():
            row_str = " ".join(str(v) for v in row.values)
            vals = _extract_numeric_values(row)

            if any(kw in row_str for kw in ["1年以内", "一年以内"]):
                result["within_1y"] = _pick_best_value(vals)
            elif any(kw in row_str for kw in ["1至2年", "1-2年", "一至二年"]):
                result["1_to_2y"] = _pick_best_value(vals)
            elif any(kw in row_str for kw in ["2至3年", "2-3年", "二至三年"]):
                result["2_to_3y"] = _pick_best_value(vals)
            elif any(kw in row_str for kw in ["3年以上", "三年以上"]):
                result["over_3y"] = _pick_best_value(vals)
            elif "合计" in row_str:
                result["total"] = _pick_best_value(vals)

        if result.get("total") and result.get("within_1y"):
            result["within_1y_pct"] = round(
                result["within_1y"] / result["total"] * 100, 1)
            return result

    return None


# ============================================================
# ============================================================
# 7. 客户集中度（前五客户销售占比）
# ============================================================

def extract_customer_concentration(pdf_path: str | Path) -> dict | None:
    """提取前五名客户销售占比。

    搜索关键词: "前五名客户"、"前五大客户"、"主要客户"、"客户集中"
    年报附注标准披露格式：前五名客户销售额 / 占年度销售总额比例

    Returns:
        {"top5_ratio": 前五占比(%), "top1_ratio": 第一大占比(%),
         "customer_count": 客户数量}
    """
    tables = extract_tables(pdf_path, pages="all", method="auto")

    for df in tables:
        text_flat = " ".join(df.astype(str).values.flatten())
        # 必须包含客户集中度相关关键词
        if not any(kw in text_flat for kw in [
            "前五名客户", "前五大客户", "主要客户", "客户集中",
            "前五名销售", "前五大销售"
        ]):
            continue

        # 必须有百分比或比例
        if "比例" not in text_flat and "%" not in text_flat:
            continue

        result = {}
        ratios = []
        for _, row in df.iterrows():
            row_str = " ".join(str(v) for v in row.values)
            vals = _extract_numeric_values(row)

            # 找占比值：通常在 0-100 之间的数
            pct_vals = [v for v in vals if 0 < v <= 100]

            if any(kw in row_str for kw in ["合计", "总计", "前五", "前5"]):
                ratios.extend(pct_vals)
            elif any(kw in row_str for kw in ["第一名", "客户一", "客户1"]):
                if pct_vals:
                    result["top1_ratio"] = max(pct_vals)
            elif "比例" in row_str.lower() or "%" in row_str:
                ratios.extend(pct_vals)

        # 取合理范围内的值作为前五占比（排除合计行100%）
        valid_ratios = [r for r in ratios if 5 <= r <= 99]
        if valid_ratios:
            result["top5_ratio"] = max(valid_ratios)
            result["customer_count"] = 5
            return result

    return None


# ============================================================
# 工具函数
# ============================================================

def _extract_numeric_values(row: pd.Series) -> list[float]:
    """从一行中提取所有数值。"""
    vals = []
    for v in row.values:
        try:
            if isinstance(v, (int, float)):
                if not np.isnan(v):
                    vals.append(float(v))
            elif isinstance(v, str):
                # 去掉千分位逗号和百分号
                clean = v.replace(",", "").replace("%", "").replace(" ", "").strip()
                if clean:
                    val = float(clean)
                    vals.append(val)
        except (ValueError, TypeError):
            continue
    return vals


def _pick_best_value(vals: list[float]) -> float | None:
    """从数值列表中选择最可能的值（中间值优先，排除极端）。"""
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]

    # 排除 0 和过大值 (>1e12)
    valid = [v for v in vals if 0 < abs(v) < 1e12]
    if not valid:
        return None
    # 取中位数附近的
    valid.sort()
    return valid[len(valid) // 2]
