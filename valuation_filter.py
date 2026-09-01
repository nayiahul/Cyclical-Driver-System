"""估值排雷 — 硬约束，不参与Alpha评分

Gate 3 (2026-09-01):
  - 修复 P2-001: 价格源从空目录 data/cache/daily_prices/ 改指 STOCKS_DIR
  - 乖离率/流动性迁移到 MarketData.as_of（PIT 截断）
  - 此前两规则因数据源指向空目录从未生效（Feature Activation）
"""
import os
import numpy as np
import pandas as pd
from loguru import logger

from config.params import PEG_MAX, STOCKS_DIR
from data_governance import filter_available_reports_dash
from pit.market import MarketData

_MARKET = MarketData()


def _load_price_data(code: str) -> pd.DataFrame:
    """加载个股日线缓存（Gate 3: 指向 STOCKS_DIR，修复 P2-001 空目录问题）"""
    path = f"{STOCKS_DIR}/{code}.csv"
    if os.path.exists(path):
        df = pd.read_csv(path, dtype={"date": str})
        df["date"] = df["date"].str.replace("-", "", regex=False)
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        return df.set_index("date").sort_index()
    return pd.DataFrame()


def _load_fin_data() -> pd.DataFrame:
    """加载财务数据缓存"""
    path = "data/cache/financial_data.csv"
    if os.path.exists(path):
        return pd.read_csv(path, dtype={"code": str})
    return pd.DataFrame()


def apply_valuation_filter(t_date: str, codes: list[str],
                          industry_map: dict = None) -> list[str]:
    """
    估值排雷硬约束。返回通过过滤的股票列表。

    规则:
    1. PE负且近两季ROE未改善 → 剔除
    2. 非经常性损益依赖(ROE波动>50%) → 剔除
    3. 乖离率>120% → 剔除
    4. PEG>PEG_MAX → 剔除
    5. 流动性后20% → 剔除
    6. 连续3期经营现金流为负 (R035) → 剔除
    7. 商誉/净资产 > 30% (R008) → 剔除
    8. 存贷双高: 货币资金>5亿+有息负债>1亿+现金/负债<2 (R010) → 剔除
    """
    removed = {"neg_pe": 0, "nonrecurring": 0, "deviation": 0, "peg": 0,
               "liquidity": 0, "cash_burn": 0, "goodwill": 0, "double_high": 0}
    fin = _load_fin_data()
    if not fin.empty:
        fin = filter_available_reports_dash(fin, "date", t_date)
        fin["date"] = pd.to_datetime(fin["date"])
        fin_cutoff = fin
        # Gate 0-A: 按 code 预分组（无语义变更）
        fin_by_code = {c: g for c, g in fin_cutoff.groupby("code")}
        _EMPTY_FIN = fin_cutoff.iloc[0:0].copy()
    else:
        fin_cutoff = fin
        fin_by_code = {}
        _EMPTY_FIN = pd.DataFrame()

    # R035: 预加载 TDX 经营现金流数据（Gate 0-A: 共享加载，无语义变更）
    from data_governance import filter_available_reports, load_tdx_raw
    tdx = load_tdx_raw()
    if tdx is not None:
        tdx = filter_available_reports(tdx, t_date)
        # Gate 0-A: 按 code 预分组，消除 29万行 × N 次全表过滤（无语义变更）
        tdx_by_code = {c: g.sort_values("report_date_str") for c, g in tdx.groupby("code")}
        _EMPTY_TDX = tdx.iloc[0:0].copy()

    # R008/R010: 预加载质量缓存 (westock-data)
    quality_path = "data/cache/quality_snapshot.csv"
    quality = None
    if os.path.exists(quality_path):
        quality = pd.read_csv(quality_path, dtype={"code": str, "report_date": str})
        # Gate 0-A: 按 code 预分组（无语义变更）
        quality_by_code = {c: g for c, g in quality.groupby("code")}
        _EMPTY_Q = quality.iloc[0:0].copy()

    passed = []
    for code in codes:
        code_fin = fin_by_code.get(code, _EMPTY_FIN) if fin_by_code else pd.DataFrame()
        roe = code_fin["roe_weighted"].dropna() if not code_fin.empty else pd.Series(dtype=float)

        # 规则1: PE负且近两季ROE未改善
        if len(roe) >= 3:
            latest = roe.iloc[-1]
            prev = roe.iloc[-3]
            if latest < 0 and latest <= prev:
                removed["neg_pe"] += 1
                continue

        # 规则2: 非经常性损益依赖 (ROE波动过大)
        if len(roe) >= 4:
            roe_std = roe.tail(4).std()
            roe_mean = roe.tail(4).mean()
            if roe_mean > 0 and roe_std / roe_mean > 1.0:
                removed["nonrecurring"] += 1
                continue

        # 规则3: 乖离率 > 120%（Gate 3: PIT 截断 + 数据源修复，规则恢复生效）
        df = _MARKET.as_of(code, t_date)
        if len(df) >= 200:
            close = df["close"]
            ma200 = close.rolling(200).mean().iloc[-1]
            last_close = close.iloc[-1]
            if ma200 > 0 and (last_close - ma200) / ma200 > 1.20:
                removed["deviation"] += 1
                continue

        # 规则4: PEG > PEG_MAX
        # v1.1: 仅当 ROE 改善时判断 (roe_recent > roe_past)
        # PEG = PE / growth, growth = ROE_TTM增长率 (%), cap [5, 50]
        # PE_approx = 100 / ROE_recent (排雷层运行在 S1 计算之前)
        if len(roe) >= 8:
            roe_recent = roe.tail(4).mean()
            roe_past = roe.tail(8).head(4).mean()
            if roe_past > 0 and roe_recent > 0 and roe_recent > roe_past:
                growth = (roe_recent / roe_past - 1) * 100
                growth = max(5, min(50, growth))  # cap 防爆炸
                pe_approx = 100.0 / roe_recent
                peg = pe_approx / growth
                if peg > PEG_MAX:
                    removed["peg"] += 1
                    continue

        # 规则6: R035 — 连续3期经营现金流为负 (TDX col 107)
        if tdx is not None:
            ctdx = tdx_by_code.get(code, _EMPTY_TDX)
            ocf = ctdx["operating_cash_flow"].dropna().values.astype(float)
            if len(ocf) >= 3:
                if ocf[-1] < 0 and ocf[-2] < 0 and ocf[-3] < 0:
                    removed["cash_burn"] += 1
                    continue

        # 规则7: R008 — 商誉/净资产 > 30% (westock-data zcfz)
        if quality is not None:
            qrow = quality_by_code.get(code, _EMPTY_Q)
            if len(qrow) > 0:
                gw = qrow.iloc[0]["goodwill"]
                eq = qrow.iloc[0]["equity"]
                if (gw is not None and eq is not None and not pd.isna(gw) and not pd.isna(eq)
                        and eq > 0 and gw > 0):
                    if gw / eq > 0.30:
                        removed["goodwill"] += 1
                        continue

        # 规则8: R010 — 存贷双高 (货币资金>5亿 + 有息负债>1亿 + 现金/负债<1.0)
        # 排除 银行/非银/公用事业(行业性高杠杆)
        if quality is not None:
            ind = industry_map.get(code, "")
            skip_ind = {"银行", "非银金融", "公用事业"}
            if ind not in skip_ind:
                qrow2 = quality_by_code.get(code, _EMPTY_Q)
                if len(qrow2) > 0:
                    cash = qrow2.iloc[0]["cash_equivalents"]
                    debt = qrow2.iloc[0]["interest_bear_debt"]
                    if (cash is not None and debt is not None and not pd.isna(cash) and not pd.isna(debt)):
                        if cash > 5e8 and debt > 1e8 and cash / debt < 1.0:
                            removed["double_high"] += 1
                            continue

        passed.append(code)

    # 规则5: 流动性后20%（Gate 3: PIT 截断 + 数据源修复，规则恢复生效）
    market_caps = {}
    for code in passed:
        df = _MARKET.as_of(code, t_date)
        if len(df) >= 20:
            close = df["close"].iloc[-1]
            volume = df["volume"].mean() if "volume" in df.columns else 1e6
            market_caps[code] = close * volume

    if len(market_caps) > 0:
        cap_series = pd.Series(market_caps)
        threshold = cap_series.quantile(0.20)
        before = len(passed)
        passed = [c for c in passed if c not in market_caps or market_caps[c] >= threshold]
        removed["liquidity"] = before - len(passed)

    total_removed = sum(removed.values())
    logger.info(
        f"估值排雷 @ {t_date}: {len(codes)}→{len(passed)} "
        f"(剔除: {removed})"
    )
    if removed.get("cash_burn", 0) > 0:
        logger.info(f"  R035 失血剔除: {removed['cash_burn']} 只")
    return passed
