"""通达信财务数据批量提取器

从本地 gpcw*.dat 文件提取 S1/S2 所需字段，缓存为 CSV。
一次读取覆盖全市场 5500+ 股票，零 API 调用。
"""
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from pytdx.reader import HistoryFinancialReader

from config.tdx_fieldmap import (
    MIN_BASE_PROFIT, TDX_FIELDS, WINSORIZE_MAX, WINSORIZE_MIN,
)

TDX_ROOT = Path("/Users/nayiahlu/Downloads/tdxfin")
CACHE_PATH = "data/cache/tdx_financials.csv"
REQUIRED_PERIODS = pd.date_range("20120101", "20260630", freq="QE-DEC")
VALID_PREFIXES = ("600", "601", "602", "603", "605",
                   "000", "001", "002", "003",
                   "300", "301", "688", "689")


def _discover_files(root: Path) -> dict[str, Path]:
    """扫描目录，返回 {report_period: file_path}。只取 .dat 文件。"""
    files = {}
    for p in root.iterdir():
        if not p.name.startswith("gpcw"):
            continue
        if not p.name.endswith(".dat"):
            continue
        if p.stat().st_size == 0:
            continue
        # 提取日期: gpcw20241231.dat → 20241231
        date_str = p.stem.replace("gpcw", "")
        if len(date_str) == 8 and date_str.isdigit():
            files[date_str] = p
    return files


def _winsorize(series: pd.Series, lo: float = WINSORIZE_MIN, hi: float = WINSORIZE_MAX) -> pd.Series:
    """Winsorize at given percentiles."""
    lo_val = series.quantile(lo / 100)
    hi_val = series.quantile(hi / 100)
    return series.clip(lo_val, hi_val)


def _validate_fields(df: pd.DataFrame) -> list[str]:
    """检查关键字段，返回异常字段列表。"""
    issues = []
    critical = ["deducted_profit_yoy", "deducted_profit_q", "contract_liabilities"]
    for col in critical:
        if col not in df.columns:
            issues.append(f"MISSING: {col}")
            continue
        non_null = df[col].notna().sum()
        total = len(df)
        pct = non_null / total * 100 if total > 0 else 0
        if pct < 90:
            issues.append(f"LOW_COVERAGE: {col} = {pct:.1f}%")
    return issues


def load_tdx_financials(force_rebuild: bool = False) -> pd.DataFrame:
    """
    主函数：加载/构建通达信财务数据缓存。

    Returns:
        DataFrame with columns:
        code, report_date, [all fields from TDX_FIELDS],
        report_date_str (YYYYMMDD)
    """
    if os.path.exists(CACHE_PATH) and not force_rebuild:
        logger.info(f"从缓存加载: {CACHE_PATH}")
        df = pd.read_csv(CACHE_PATH, dtype={"code": str, "report_date_str": str})
        return df

    files = _discover_files(TDX_ROOT)
    logger.info(f"发现 {len(files)} 个 gpcw 文件")

    if not files:
        raise FileNotFoundError(f"在 {TDX_ROOT} 中未找到 gpcw*.dat 文件")

    reader = HistoryFinancialReader()
    frames = []
    col_names = [f"col{v['col']}" for v in TDX_FIELDS.values()]
    col_to_name = {f"col{v['col']}": name for name, v in TDX_FIELDS.items()}

    for date_str in sorted(files.keys()):
        filepath = files[date_str]
        try:
            df = reader.get_df(str(filepath))
        except Exception as e:
            logger.warning(f"读取 {filepath.name} 失败: {e}")
            continue

        if df is None or df.empty:
            continue

        # Stock code is in the index
        df = df.reset_index()
        if "code" not in df.columns and df.index.name == "code":
            df["code"] = df.index

        if "code" not in df.columns:
            continue

        # Filter valid A-share codes
        df["code"] = df["code"].astype(str).str.zfill(6)
        df = df[df["code"].str.startswith(VALID_PREFIXES)]

        # Extract required columns
        available = ["code"]
        for cn in col_names:
            if cn in df.columns:
                df[cn] = pd.to_numeric(df[cn], errors="coerce")
                available.append(cn)

        if len(available) < 3:
            continue

        subset = df[available].copy()
        subset["report_date"] = pd.to_datetime(date_str, format="%Y%m%d")
        frames.append(subset)

    if not frames:
        raise RuntimeError("未能从任何 gpcw 文件中提取数据")

    result = pd.concat(frames, ignore_index=True)
    result = result.rename(columns=col_to_name)

    # Unit conversion: 合同负债 万元→元
    if "contract_liabilities" in result.columns:
        result["contract_liabilities"] = result["contract_liabilities"] * 10000
        result["contract_liabilities"] = result["contract_liabilities"].fillna(0.0)

    if "contract_assets" in result.columns:
        result["contract_assets"] = result["contract_assets"] * 10000
        result["contract_assets"] = result["contract_assets"].fillna(0.0)

    # Winsorize growth rate columns
    for name, spec in TDX_FIELDS.items():
        if "valid_range" in spec and name in result.columns:
            lo, hi = spec["valid_range"]
            result[name] = result[name].clip(lo, hi)

    # Winsorize absolute value columns
    for name in ["deducted_profit_q", "operating_profit", "revenue"]:
        if name in result.columns:
            result[name] = _winsorize(result[name])

    result["report_date_str"] = result["report_date"].dt.strftime("%Y%m%d")

    # Sort and deduplicate (keep latest if duplicate report period exists)
    result = result.sort_values(["code", "report_date"]).drop_duplicates(
        subset=["code", "report_date_str"], keep="last"
    )

    # Validate
    issues = _validate_fields(result)
    if issues:
        for issue in issues:
            logger.warning(f"数据质量: {issue}")

    # Save cache
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    result.to_csv(CACHE_PATH, index=False)
    n_codes = result["code"].nunique()
    n_periods = result["report_date_str"].nunique()
    logger.info(f"TDX财务缓存已保存: {len(result)} 行, {n_codes} 只股票, {n_periods} 个报告期")

    return result


def get_quarterly_data(t_date: str) -> pd.DataFrame:
    """
    获取截至 t_date 的最新财务数据快照。

    Returns DataFrame with point-in-time data (只取 <= t_date 的报告期)。
    """
    df = load_tdx_financials()
    df = df[df["report_date_str"] <= t_date]
    # 取每只股票的最新报告期
    latest = df.sort_values("report_date").groupby("code").last().reset_index()
    return latest


if __name__ == "__main__":
    df = load_tdx_financials(force_rebuild=True)
    print(f"Done: {len(df)} rows, cols={list(df.columns)}")
