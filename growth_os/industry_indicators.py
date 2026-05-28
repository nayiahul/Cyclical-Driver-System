"""行业领先指标 — 产业数据层，验证"营收增速是否来自真实的行业扩张"。

纯财务探针已被证明是反向指标(3G0R=-9.6%)，产业层数据提供外部验证。

数据源: akshare 宏观/行业 API，月频为主，带缓存避免重复请求。
"""
from __future__ import annotations
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from loguru import logger

# 缓存: {api_name: (fetch_time, dataframe)}
_cache: dict = {}
_CACHE_TTL = timedelta(hours=6)  # 月频数据，6小时缓存足够


def _cached_fetch(api_name: str, fetcher, **kwargs):
    """带缓存的 akshare API 调用。"""
    now = datetime.now()
    key = f"{api_name}_{str(kwargs)}"
    if key in _cache:
        ts, df = _cache[key]
        if now - ts < _CACHE_TTL:
            return df
    try:
        df = fetcher(**kwargs)
        _cache[key] = (now, df)
        return df
    except Exception as e:
        logger.warning(f"行业指标获取失败 {api_name}: {e}")
        # 返回过期缓存（如果有）
        if key in _cache:
            _, old_df = _cache[key]
            return old_df
        return None


# ═══════════════════════════════════════════════
# 1. 产业周期热度
# ═══════════════════════════════════════════════

def get_industry_cycle_signal(t_date: str = None) -> dict:
    """聚合 PMI / 工业增加值 / 出口 / 用电量 → 0-100 产业周期热度分。

    Returns:
        {"score": 0-100, "phase": "expansion"|"neutral"|"contraction",
         "details": {"pmi": float, "ip_yoy": float, "export_yoy": float, "power_yoy": float}}
    """
    details = {}
    score = 0

    # 1. 制造业 PMI (25-35分)
    try:
        import akshare as ak
        df = _cached_fetch("pmi", ak.macro_china_pmi_yearly)
        if df is not None and len(df) > 0:
            pmi = float(df["今值"].dropna().iloc[-1])
            details["pmi"] = pmi
            if pmi > 52:
                score += 35
            elif pmi > 50:
                score += 25
            elif pmi > 48:
                score += 10
    except Exception as e:
        logger.debug(f"PMI获取失败: {e}")

    # 2. 工业增加值 yoy (20-30分)
    try:
        import akshare as ak
        df = _cached_fetch("ip", ak.macro_china_industrial_production_yoy)
        if df is not None and len(df) > 0:
            ip = float(df["今值"].dropna().iloc[-1])
            details["ip_yoy"] = ip
            if ip > 8:
                score += 30
            elif ip > 5:
                score += 20
            elif ip > 3:
                score += 10
    except Exception as e:
        logger.debug(f"工业增加值获取失败: {e}")

    # 3. 出口增速 yoy (15-25分)
    try:
        import akshare as ak
        df = _cached_fetch("export", ak.macro_china_exports_yoy)
        if df is not None and len(df) > 0:
            export = float(df["今值"].dropna().iloc[-1])
            details["export_yoy"] = export
            if export > 10:
                score += 25
            elif export > 5:
                score += 15
            elif export > 0:
                score += 5
    except Exception as e:
        logger.debug(f"出口数据获取失败: {e}")

    # 4. 第二产业用电量 yoy (15-25分)
    try:
        import akshare as ak
        df = _cached_fetch("power", ak.macro_china_society_electricity)
        if df is not None and len(df) > 0 and "第二产业用电量同比" in df.columns:
            power = float(df["第二产业用电量同比"].dropna().iloc[-1])
            details["power_yoy"] = power
            if power > 6:
                score += 25
            elif power > 3:
                score += 15
            elif power > 1:
                score += 5
    except Exception as e:
        logger.debug(f"用电量获取失败: {e}")

    # 确定阶段
    if score >= 60:
        phase = "expansion"
    elif score >= 35:
        phase = "neutral"
    else:
        phase = "contraction"

    return {"score": score, "phase": phase, "details": details}


# ═══════════════════════════════════════════════
# 2. 行业动量（基于行业板块指数）
# ═══════════════════════════════════════════════

# 申万三级行业 → 东方财富行业板块 映射（部分）
_INDUSTRY_TO_BOARD = {
    "通信网络设备及器件": "通信设备",
    "横向通用软件": "软件开发",
    "垂直应用软件": "软件开发",
    "游戏": "游戏",
    "半导体设备": "半导体",
    "数字芯片设计": "半导体",
    "集成电路封测": "半导体",
    "医疗耗材": "医疗器械",
    "医疗设备": "医疗器械",
    "化学制剂": "化学制药",
    "其他生物制品": "生物制品",
    "中药": "中药",
    "光伏电池组件": "光伏设备",
    "光伏辅材": "光伏设备",
    "锂电池": "电池",
    "电池化学品": "电池",
    "军工电子": "军工电子",
    "航空装备": "航天航空",
    "底盘与发动机系统": "汽车零部件",
    "其他汽车零部件": "汽车零部件",
    "消费电子零部件及组装": "消费电子",
    "光学元件": "光学光电子",
    "铝": "有色金属",
    "铜": "有色金属",
    "黄金": "贵金属",
    "煤炭开采": "煤炭行业",
    "逆变器": "电源设备",
    "其他电源设备": "电源设备",
    "风电整机": "风电设备",
    "工控设备": "专用设备",
    "其他专用设备": "专用设备",
    "食品及饲料添加剂": "食品饮料",
    "白酒": "酿酒行业",
}


def get_industry_momentum(industry_l3: str, t_date: str = None) -> dict:
    """获取行业板块相对强度。

    通过东方财富行业板块指数计算近3月涨幅 vs 沪深300。

    Returns:
        {"momentum": "leading"|"inline"|"lagging",
         "board_return_3m": float, "hs300_return_3m": float, "label": str}
    """
    board_name = _INDUSTRY_TO_BOARD.get(industry_l3)
    if not board_name:
        return {"momentum": "unknown", "board_return_3m": None,
                "hs300_return_3m": None, "label": f"⚪ 行业动量：无板块映射({industry_l3})"}

    try:
        import akshare as ak

        # 行业板块历史数据
        df_board = _cached_fetch(
            f"board_hist_{board_name}",
            ak.stock_board_industry_hist_em,
            symbol=board_name, period="月k", adjust=""
        )
        if df_board is None or len(df_board) < 4:
            return {"momentum": "unknown", "board_return_3m": None,
                    "hs300_return_3m": None, "label": f"⚪ 行业动量：{board_name}数据不足"}

        # 近3月行业涨幅
        board_recent = df_board["收盘"].iloc[-1]
        board_3m_ago = df_board["收盘"].iloc[-4] if len(df_board) >= 4 else df_board["收盘"].iloc[0]
        board_ret = (board_recent / board_3m_ago - 1) * 100

        # 沪深300近3月涨幅（用上证指数近似）
        df_hs = _cached_fetch(
            "hs300_hist",
            ak.stock_zh_index_daily,
            symbol="sh000300"
        )
        if df_hs is not None and len(df_hs) >= 63:
            hs_recent = df_hs["close"].iloc[-1]
            hs_3m_ago = df_hs["close"].iloc[-63]
            hs_ret = (hs_recent / hs_3m_ago - 1) * 100
        else:
            hs_ret = 0

        spread = board_ret - hs_ret
        if spread > 5:
            momentum = "leading"
            label = f"🟢 行业领先（{board_name}+{board_ret:.0f}% vs HS300+{hs_ret:.0f}%，超额{spread:.0f}%）"
        elif spread > -5:
            momentum = "inline"
            label = f"🟡 行业同步（{board_name}+{board_ret:.0f}% vs HS300+{hs_ret:.0f}%）"
        else:
            momentum = "lagging"
            label = f"🔴 行业落后（{board_name}+{board_ret:.0f}% vs HS300+{hs_ret:.0f}%，落后{abs(spread):.0f}%）"

        return {"momentum": momentum, "board_return_3m": round(board_ret, 1),
                "hs300_return_3m": round(hs_ret, 1), "label": label}

    except Exception as e:
        logger.debug(f"行业动量获取失败 {industry_l3}: {e}")
        return {"momentum": "unknown", "board_return_3m": None,
                "hs300_return_3m": None, "label": f"⚪ 行业动量：API异常"}


# ═══════════════════════════════════════════════
# 3. 增长质量验证
# ═══════════════════════════════════════════════

# 行业营收增速基准（申万三级行业近3年平均营收增速，基于全A统计）
# 简化版：用工业增加值/PMI作为工业类行业的代理，服务业用非制造业PMI
_INDUSTRIAL_SECTORS = {
    "通信网络设备及器件", "半导体设备", "数字芯片设计", "集成电路封测",
    "光伏电池组件", "光伏辅材", "锂电池", "电池化学品", "风电整机",
    "军工电子", "航空装备", "底盘与发动机系统", "其他汽车零部件",
    "消费电子零部件及组装", "光学元件", "铝", "铜", "黄金",
    "煤炭开采", "逆变器", "其他电源设备", "工控设备", "其他专用设备",
    "金属制品", "线缆部件及其他", "化学制剂", "其他化学原料", "其他化学制品",
}


def validate_growth_quality(
    code: str, industry_l3: str, revenue_yoy: float, t_date: str = None
) -> dict:
    """将公司营收增速与宏观经济指标交叉验证。

    Returns:
        {"quality": "strong_alpha"|"alpha"|"beta"|"share_loss",
         "benchmark_growth": float, "label": str}
    """
    # 获取宏观基准增速
    cycle = get_industry_cycle_signal(t_date)
    details = cycle.get("details", {})

    is_industrial = industry_l3 in _INDUSTRIAL_SECTORS

    if is_industrial:
        benchmark = details.get("ip_yoy", 5.0)  # 工业增加值
        benchmark_label = f"工业增加值+{benchmark:.1f}%"
    else:
        # 服务业用非制造业PMI隐含增速
        pmi = details.get("pmi", 50)
        benchmark = max(0, (pmi - 50) * 1.5)  # PMI 52 → 3%, PMI 55 → 7.5%
        benchmark_label = f"服务业PMI隐含+{benchmark:.1f}%"

    if revenue_yoy is None or benchmark <= 0:
        return {"quality": "unknown", "benchmark_growth": round(benchmark, 1),
                "label": "⚪ 增长质量：基准数据不足"}

    ratio = revenue_yoy / benchmark if benchmark > 0 else float("inf")

    if ratio > 1.5:
        quality = "strong_alpha"
        label = (f"🟢 显著超越行业（公司+{revenue_yoy:.0f}% vs {benchmark_label}，"
                 f"超额{revenue_yoy-benchmark:.0f}pp）→ 强α驱动")
    elif ratio > 1.0:
        quality = "alpha"
        label = (f"🟢 超越行业（公司+{revenue_yoy:.0f}% vs {benchmark_label}）→ 有α")
    elif ratio > 0.5:
        quality = "beta"
        label = (f"🟡 与行业同步（公司+{revenue_yoy:.0f}% vs {benchmark_label}）→ β驱动")
    else:
        quality = "share_loss"
        label = (f"🔴 落后行业（公司+{revenue_yoy:.0f}% vs {benchmark_label}）→ 份额丢失")

    return {"quality": quality, "benchmark_growth": round(benchmark, 1), "label": label}
