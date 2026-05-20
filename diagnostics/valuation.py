"""多估值体系 — 行业特化估值方法

银行/非银 → PB (市净率)
周期行业 → EV/EBITDA
PE无效 → PS (市销率)
其余    → PE (TTM, 当前)

所有方法均使用行业内分位排名，保持跨行业可比性。
"""
import os

import numpy as np
import pandas as pd

# 行业分组
PB_INDUSTRIES = {"银行", "非银金融"}
EV_EBITDA_INDUSTRIES = {
    "煤炭", "钢铁", "有色金属", "基础化工",
    "石油石化", "建筑材料", "交通运输",
}
# PS 用于 PE 无效时 (PE<=0 or PE>200)


def compute_valuation_scores(codes: list[str],
                              industry_map: dict,
                              ttm_eps_map: dict,
                              t_date: str) -> dict:
    """
    计算每个 code 的估值指标和行业内分位得分。

    Returns:
        {code: (val_ratio, val_score)}  # val_score 同 PE 分位映射到 [-2,3]
    """
    # 预加载额外数据
    quality = _load_quality()
    tdx = _load_tdx_snapshot(t_date)

    # 逐股计算估值指标
    ratios = {}
    for code in codes:
        ind = industry_map.get(code, "未知")
        method = _pick_method(ind, code, ttm_eps_map)
        ratio = _compute_ratio(code, method, ttm_eps_map, quality, tdx)
        if ratio is not None:
            ratios[code] = (method, ratio)

    # 行业内分位排名
    scores = {}
    # 按行业分组排名
    ind_ratios = {}
    for code, (method, ratio) in ratios.items():
        ind = industry_map.get(code, "未知")
        if ind not in ind_ratios:
            ind_ratios[ind] = []
        ind_ratios[ind].append((code, ratio))

    for ind, items in ind_ratios.items():
        if len(items) < 5:
            for code, _ in items:
                scores[code] = (ratios[code][1], 0.0)
            continue
        # 分位排名 (ratio 越低越便宜)
        sorted_vals = sorted([r for _, r in items])
        for code, ratio in items:
            pct = sum(1 for v in sorted_vals if v >= ratio) / len(sorted_vals)
            val_score = (pct - 0.5) * 4
            scores[code] = (ratio, round(val_score, 3))

    return scores


def _pick_method(ind: str, code: str, ttm_eps_map: dict) -> str:
    """选择估值方法。"""
    if ind in PB_INDUSTRIES:
        return "PB"
    if ind in EV_EBITDA_INDUSTRIES:
        return "EV_EBITDA"
    # PE 无效时 fallback 到 PS
    eps = ttm_eps_map.get(code)
    if eps is None or np.isnan(eps) or eps <= 0.01:
        return "PS"
    return "PE"


def _compute_ratio(code, method, ttm_eps_map, quality, tdx) -> float | None:
    """计算估值比率。"""
    from signals import _load_price_data
    df_price = _load_price_data(code)
    if len(df_price) == 0:
        return None
    price = float(df_price["close"].iloc[-1])

    # 市值
    shares = _get_tdx_field(tdx, code, "total_shares")
    if shares is None or shares <= 0:
        return None
    mcap = price * shares

    if method == "PB":
        eq = _get_quality_field(quality, code, "equity")
        if eq is None or eq <= 0:
            # fallback to PE
            eps = ttm_eps_map.get(code)
            return price / eps if eps and eps > 0 else None
        return mcap / eq

    if method == "EV_EBITDA":
        ebitda = _estimate_ebitda(tdx, code)
        if ebitda is None or ebitda <= 0:
            eps = ttm_eps_map.get(code)
            return price / eps if eps and eps > 0 else None
        debt = _get_quality_field(quality, code, "interest_bear_debt") or 0
        cash = _get_quality_field(quality, code, "cash_equivalents") or 0
        ev = mcap + debt - cash
        return ev / ebitda if ev > 0 else None

    if method == "PS":
        rev = _get_tdx_field(tdx, code, "revenue")
        if rev is None or rev <= 0:
            return None
        return mcap / rev

    # PE (default)
    eps = ttm_eps_map.get(code)
    if eps is None or eps <= 0:
        return None
    ratio = price / eps
    return min(200, max(1, ratio))


def _estimate_ebitda(tdx, code) -> float | None:
    """估算 EBITDA ≈ 营业利润 + 折旧(用固定资产×5%近似)"""
    op = _get_tdx_field(tdx, code, "operating_profit")
    fa = _get_tdx_field(tdx, code, "fixed_assets")
    if op is None:
        return None
    depr = fa * 0.05 if fa else 0
    return op + depr


def _get_tdx_field(tdx, code, field) -> float | None:
    if tdx is None:
        return None
    row = tdx[tdx["code"] == code]
    if len(row) == 0:
        return None
    val = row.iloc[0].get(field)
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _get_quality_field(quality, code, field) -> float | None:
    if quality is None:
        return None
    row = quality[quality["code"] == code]
    if len(row) == 0:
        return None
    val = row.iloc[0].get(field)
    try:
        v = float(val)
        return v if not pd.isna(v) else None
    except (ValueError, TypeError):
        return None


def _load_quality() -> pd.DataFrame | None:
    path = "data/cache/quality_snapshot.csv"
    if os.path.exists(path):
        return pd.read_csv(path, dtype={"code": str, "report_date": str})
    return None


def _load_tdx_snapshot(t_date: str) -> pd.DataFrame | None:
    """加载 TDX 最新快照（仅最近一期，用于取总股本/营收等）。"""
    path = "data/cache/tdx_financials.csv"
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, dtype={"code": str, "report_date_str": str})
    from data_governance import filter_available_reports
    df = filter_available_reports(df, t_date)
    # 每只股票取最新报告期
    latest = df.sort_values("report_date_str").groupby("code").last().reset_index()
    return latest
