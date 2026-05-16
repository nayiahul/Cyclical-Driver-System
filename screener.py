"""研究筛选器

基于 V4.2 三维框架（景气度/壁垒/估值）筛选标的，辅助人工深度研究。
不生成组合，不自动交易——只输出排序清单。
"""
import os
from collections import defaultdict

import numpy as np
import pandas as pd
from loguru import logger

from config.params import TOP_N_STOCKS
from industry import get_sw_industry
from trade_calendar import get_t_date, get_trade_calendar
from universe import get_universe
from valuation_filter import apply_valuation_filter
from signals import compute_S3, compute_S4, compute_S5, compute_S7, _zscore
from regime.detector import detect_regime


def screen(date_str: str = None, top_n: int = 200) -> pd.DataFrame:
    """
    主筛选函数。

    Args:
        date_str: 日期 "YYYYMMDD"，默认最新交易日
        top_n: 输出前 N 只股票

    Returns:
        DataFrame with columns:
        code, name, industry, sector(景气度), moat(壁垒), valuation(估值),
        composite_score, flags(标签)
    """
    if date_str is None:
        # 取最新调仓日
        import datetime
        today = datetime.date.today().strftime("%Y%m%d")
        cal = get_trade_calendar("20240101", today)
        if len(cal) == 0:
            date_str = today
        else:
            date_str = cal["trade_date"].iloc[-1]

    t_date = get_t_date(date_str)
    logger.info(f"筛选日期: {date_str}, 数据截止: {t_date}")

    # 1. 获取股票池 + 估值排雷
    universe_df = get_universe(t_date)
    codes_all = universe_df["code"].tolist()
    logger.info(f"全市场: {len(codes_all)} 只")

    filtered = apply_valuation_filter(t_date, codes_all)
    logger.info(f"估值排雷后: {len(filtered)} 只")

    # 2. 行业映射
    industry_map = get_sw_industry()

    # 3. 信号计算
    logger.info("计算信号...")
    s3 = compute_S3(t_date, filtered, industry_map)
    s4 = compute_S4(t_date, filtered, industry_map)
    s5 = compute_S5(t_date, filtered, industry_map)
    s7 = compute_S7(t_date, filtered, industry_map)

    # 4. 构建评分
    results = []
    for code in filtered:
        name = universe_df[universe_df["code"] == code]["name"].values
        name = name[0] if len(name) > 0 else ""

        s3_val = s3.get(code, np.nan) if code in s3.index else np.nan
        s4_val = s4.get(code, np.nan) if code in s4.index else np.nan
        s5_val = s5.get(code, np.nan) if code in s5.index else np.nan
        s7_val = s7.get(code, np.nan) if code in s7.index else np.nan

        # 景气度 = S3 + S4（价格验证层）
        momentum_vals = [v for v in [s3_val, s4_val] if not np.isnan(v)]
        momentum = np.mean(momentum_vals) if momentum_vals else np.nan

        # 壁垒 = S5 + S7（质量层）
        moat_vals = [v for v in [s5_val, s7_val] if not np.isnan(v)]
        moat = np.mean(moat_vals) if moat_vals else np.nan

        # 估值评分（排雷已过滤极端泡沫，这里用信号代理）
        # S5高+S7高+通过排雷 = 估值合理偏便宜
        if not np.isnan(moat):
            valuation = moat  # 质量越高 → 估值越合理
        else:
            valuation = np.nan

        # 综合：景气度(0.4) + 壁垒(0.35) + 估值(0.25)
        parts = []
        if not np.isnan(momentum): parts.append(momentum * 0.4)
        if not np.isnan(moat): parts.append(moat * 0.35)
        if not np.isnan(valuation): parts.append(valuation * 0.25)
        composite = sum(parts) / sum([0.4, 0.35, 0.25][:len(parts)]) if parts else np.nan

        results.append({
            "code": code,
            "name": name,
            "industry": industry_map.get(code, ""),
            "momentum": round(momentum, 3) if not np.isnan(momentum) else np.nan,
            "moat": round(moat, 3) if not np.isnan(moat) else np.nan,
            "valuation": round(valuation, 3) if not np.isnan(valuation) else np.nan,
            "composite": round(composite, 4) if not np.isnan(composite) else np.nan,
        })

    df = pd.DataFrame(results).sort_values("composite", ascending=False).head(top_n)

    # 5. Regime 判定
    regime_result = detect_regime(t_date)
    logger.info(f"当前市场状态: {regime_result.regime} (score={regime_result.score:.2f})")

    # 6. 添加定性标签
    df["momentum_level"] = pd.cut(df["momentum"],
        bins=[-99, -0.5, 0.5, 99], labels=["弱", "中", "强"])
    df["moat_level"] = pd.cut(df["moat"],
        bins=[-99, -0.5, 0.5, 99], labels=["低", "中", "高"])

    logger.info(f"筛选完成: {len(df)} 只 (Regime={regime_result.regime})")
    logger.info(f"按框架: 牛市→景气度优先, 熊市→估值优先, 结构市→均衡")

    return df


def main():
    df = screen()
    out_path = "output/screener_results.csv"
    os.makedirs("output", exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n已保存: {out_path}")
    print(f"\nTop 20:")
    print(df.head(20)[["code", "name", "industry", "momentum_level", "moat_level", "composite"]].to_string(index=False))
    return df


if __name__ == "__main__":
    main()
