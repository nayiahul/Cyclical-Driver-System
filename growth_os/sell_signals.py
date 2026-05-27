"""卖出信号监控 — 飞轮逆转检测。

检测五大类卖出信号，每类返回 (triggered, reason)。
"""
import pandas as pd
import numpy as np
from typing import Optional
from loguru import logger

from growth_os.data import (
    get_financial_snapshot, get_quarterly_series, get_pe_ttm, get_industry,
    load_industry_map,
)
from growth_os.wacc import compute_wacc


def check_sell_signals(code: str, t_date: str) -> list[dict]:
    """检查所有卖出信号。

    Returns:
        [{signal_name, triggered(bool), severity(red/yellow), reason}]
    """
    snap = get_financial_snapshot(t_date)
    row = snap[snap["code"] == code]
    if row.empty:
        return []
    row = row.iloc[0]
    industry_l3 = get_industry(code)

    signals = []

    # ---- 1. 毛利率连续2季下滑（非行业性） ----
    gm_series = get_quarterly_series(code, "gross_margin", n_quarters=12, t_date=t_date)
    gm_decline = False
    if len(gm_series.dropna()) >= 4:
        vals = gm_series.dropna().iloc[-4:]
        if len(vals) >= 3:
            gm_decline = (vals.iloc[-1] < vals.iloc[-2] and
                          vals.iloc[-2] < vals.iloc[-3])

    # 检查是否是行业性的
    industry_wide = False
    if gm_decline:
        ind_map = load_industry_map()
        same_industry_codes = [c for c, ind in ind_map.items() if ind == industry_l3]
        decline_count = 0
        total = 0
        for c in same_industry_codes[:20]:  # 抽样
            s = get_quarterly_series(c, "gross_margin", n_quarters=4, t_date=t_date)
            if len(s.dropna()) >= 3:
                total += 1
                vals = s.dropna().iloc[-3:]
                if vals.iloc[-1] < vals.iloc[-2] and vals.iloc[-2] < vals.iloc[-3]:
                    decline_count += 1
        if total > 0 and decline_count / total > 0.5:
            industry_wide = True

    if gm_decline and not industry_wide:
        signals.append({
            "signal": "毛利率连续2季下滑",
            "triggered": True,
            "severity": "red",
            "reason": f"非行业性: 公司自身竞争力松动",
            "detail": f"最近值: {vals.iloc[-1]:.1f}%",
        })
    elif gm_decline:
        signals.append({
            "signal": "毛利率连续2季下滑",
            "triggered": True,
            "severity": "yellow",
            "reason": f"行业性下滑: 需关注是否周期见顶",
            "detail": f"最近值: {vals.iloc[-1]:.1f}%",
        })
    else:
        signals.append({
            "signal": "毛利率连续2季下滑", "triggered": False, "severity": "", "reason": ""
        })

    # ---- 2. ROIC 跌破 WACC ----
    roic = row.get("roic")
    wacc = compute_wacc(code, t_date)
    if roic is not None and wacc is not None and not pd.isna(roic) and roic < wacc:
        signals.append({
            "signal": "ROIC跌破WACC",
            "triggered": True,
            "severity": "red",
            "reason": f"扩张毁灭价值: ROIC({roic:.1f}%) < WACC({wacc:.1f}%)",
            "detail": f"差距: {roic-wacc:.1f}%",
        })
    else:
        signals.append({
            "signal": "ROIC跌破WACC", "triggered": False, "severity": "", "reason": ""
        })

    # ---- 3. 应收增速持续远超营收 ----
    recv_series = get_quarterly_series(
        code, "notes_and_acct_receivable", n_quarters=4, t_date=t_date
    )
    rev_yoy = row.get("revenue_yoy")
    recv_surge = False
    if len(recv_series.dropna()) >= 3 and rev_yoy is not None and not pd.isna(rev_yoy):
        recent_growths = []
        for i in range(1, len(recv_series)):
            if recv_series.iloc[-i] > 0:
                recent_growths.append(
                    (recv_series.iloc[-(i)] / recv_series.iloc[-(i+1)] - 1) * 100
                )
        if rev_yoy < 0:
            # 营收负增长：应收降幅应跟上营收降幅，否则=回款效率恶化
            consec_surge = sum(1 for g in recent_growths if (g - rev_yoy) > 15)
        else:
            consec_surge = sum(1 for g in recent_growths if g > rev_yoy * 1.5)
        if consec_surge >= 2:
            recv_surge = True
            signals.append({
                "signal": "应收相对营收异常刚性",
                "triggered": True,
                "severity": "yellow",
                "reason": f"增长质量恶化: 连续{consec_surge}季应收增速高于营收增速（回款效率恶化）",
                "detail": f"营收增速{rev_yoy:.1f}%",
            })
        else:
            signals.append({
                "signal": "应收增速持续远超营收", "triggered": False, "severity": "", "reason": ""
            })
    else:
        signals.append({
            "signal": "应收增速持续远超营收", "triggered": False, "severity": "", "reason": "数据不足"
        })

    # ---- 4. 合同负债连续2季下滑 ----
    contract_series = get_quarterly_series(
        code, "contract_liabilities", n_quarters=6, t_date=t_date
    )
    if len(contract_series.dropna()) >= 3:
        vals = contract_series.dropna().iloc[-3:]
        if vals.iloc[-1] < vals.iloc[-2] and vals.iloc[-2] < vals.iloc[-3]:
            signals.append({
                "signal": "合同负债连续2季下滑",
                "triggered": True,
                "severity": "yellow",
                "reason": "在手订单萎缩，未来1-2季收入可见度下降",
                "detail": f"趋势: {vals.iloc[-3]:.0f}→{vals.iloc[-2]:.0f}→{vals.iloc[-1]:.0f}",
            })
        else:
            signals.append({
                "signal": "合同负债连续2季下滑", "triggered": False, "severity": "", "reason": ""
            })
    else:
        signals.append({
            "signal": "合同负债连续2季下滑", "triggered": False, "severity": "", "reason": "数据不足"
        })

    # ---- 5. 增速降档 + 高估值 ----
    pe = get_pe_ttm(code, t_date)
    rev_yoy_series = get_quarterly_series(
        code, "revenue_yoy", n_quarters=6, t_date=t_date
    ).dropna()
    if len(rev_yoy_series) >= 4 and pe is not None:
        recent = rev_yoy_series.iloc[-2:].mean()
        older = rev_yoy_series.iloc[-4:-2].mean()
        decelerating = recent < older * 0.85  # 减速>15%
        pe_high = pe > 50
        if decelerating and pe_high:
            signals.append({
                "signal": "增速降档+高估值",
                "triggered": True,
                "severity": "red",
                "reason": f"增速从{older:.1f}%降至{recent:.1f}%，但PE={pe:.0f}x仍按高增长定价",
                "detail": "杀估值风险",
            })
        else:
            signals.append({
                "signal": "增速降档+高估值", "triggered": False, "severity": "", "reason": ""
            })
    else:
        signals.append({
            "signal": "增速降档+高估值", "triggered": False, "severity": "", "reason": "数据不足"
        })

    return signals


def has_red_signal(signals: list[dict]) -> bool:
    """是否有红色卖出信号。"""
    return any(s["triggered"] and s["severity"] == "red" for s in signals)


def get_sell_summary(signals: list[dict]) -> str:
    """生成卖出信号摘要。"""
    triggered = [s for s in signals if s["triggered"]]
    if not triggered:
        return "未触发卖出信号"
    reds = [s for s in triggered if s["severity"] == "red"]
    yellows = [s for s in triggered if s["severity"] == "yellow"]
    parts = []
    if reds:
        parts.append(f"🔴 {len(reds)}个红色信号: {', '.join(s['signal'] for s in reds)}")
    if yellows:
        parts.append(f"🟡 {len(yellows)}个黄色信号: {', '.join(s['signal'] for s in yellows)}")
    return "\n".join(parts)
