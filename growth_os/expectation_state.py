"""Expectation State Engine v1 — 市场认知状态分类 (Step 9-D2)。

回答: 市场知道多少?
  E0 市场忽略 / E1 少数关注 / E2 市场确认 / E3 一致预期

v0 代理 (已实证 +6pp 增量): RPS 分位
v1 增强: 成交额 Z-score (volume/amount 20日 vs 60日)

输出: 状态标签, 不进评分 — 供 Opportunity Matrix 查表 (Lifecycle v3)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from pit.market import MarketData


@dataclass
class ExpectationResult:
    code: str
    state: str            # E0-E3
    attention: str        # LOW / MEDIUM / HIGH
    rps: Optional[float]
    vol_z: Optional[float]  # 成交额 Z-score
    drivers: list = field(default_factory=list)
    risks: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "code": self.code, "expectation_state": self.state,
            "attention": self.attention, "rps": self.rps,
            "vol_z": self.vol_z,
        }


class ExpectationStateEngine:
    """市场认知状态分类器 v1。"""

    def __init__(self):
        self._mkt = MarketData()

    def classify(self, code: str, t_date: str,
                 rps: Optional[float] = None) -> ExpectationResult:
        """单只分类。rps 由外部传入（需行业截面）；缺省时仅用成交额。"""
        drivers, risks = [], []

        # 成交额 Z-score (20日 vs 60日)
        df = self._mkt.as_of(code, t_date)
        vol_z = None
        if df is not None and len(df) >= 60 and "amount" in df.columns:
            amt = df["amount"].dropna().astype(float)
            if len(amt) >= 60:
                recent = amt.iloc[-20:].mean()
                base = amt.iloc[-60:].mean()
                std = amt.iloc[-60:].std()
                vol_z = float((recent - base) / std) if std > 0 else 0.0
        elif df is not None and len(df) >= 60 and "volume" in df.columns:
            vol = df["volume"].dropna().astype(float)
            if len(vol) >= 60:
                recent = vol.iloc[-20:].mean()
                base = vol.iloc[-60:].mean()
                std = vol.iloc[-60:].std()
                vol_z = float((recent - base) / std) if std > 0 else 0.0

        # E 状态: RPS 为主, 成交额辅助
        if rps is not None:
            if rps >= 80:
                state, attention = "E3", "HIGH"
            elif rps >= 60:
                state, attention = "E2", "HIGH"
            elif rps >= 30:
                # 30-60: 成交额放大 → E1, 否则 E0/E1 边界
                state = "E1" if (vol_z is not None and vol_z > 1.0) else "E1"
                attention = "MEDIUM"
            else:
                state = "E0" if (vol_z is None or vol_z < 1.5) else "E1"
                attention = "LOW"
            drivers.append(f"RPS {rps:.0f}")
        else:
            # 无 RPS: 纯成交额
            if vol_z is not None and vol_z > 2.0:
                state, attention = "E1", "MEDIUM"
            else:
                state, attention = "E0", "LOW"

        if vol_z is not None:
            drivers.append(f"成交额Z={vol_z:+.1f}")
            if vol_z > 2.0:
                risks.append("成交骤增（可能有事件驱动）")
            elif vol_z < -1.0:
                risks.append("成交萎缩（关注度下降）")

        return ExpectationResult(code, state, attention, rps, vol_z,
                                 drivers, risks)

    def classify_many(self, codes: list[str], t_date: str,
                      rps_map: dict = None) -> dict[str, ExpectationResult]:
        out = {}
        for c in codes:
            out[c] = self.classify(c, t_date,
                                   rps_map.get(c) if rps_map else None)
        return out


# ═══════════════════════════════════════════════════════════════
# E v2 Shadow — Attention × Expectation × Price State (Step 12-B)
# Issue 修复候选: E v1 把"价格弱"误当"认知低" (E_CALIBRATION_V1)
# Shadow only: 旁路运行, 不接管 v1 Production 决策
# ═══════════════════════════════════════════════════════════════

@dataclass
class ExpectationV2Result:
    code: str
    attention: str        # A0未关注 / A1初始 / A2高关注 / A3极热
    expectation: str      # E0-E3 (重定义: 市场相信多少, 非价格动量)
    price_state: str      # PS0新高 / PS1正常 / PS2回撤 / PS3深度回撤
    ret_252d: Optional[float]
    amt_ratio: Optional[float]
    peak_dist: Optional[float]
    drivers: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "e2_attention": self.attention,
            "e2_expectation": self.expectation,
            "e2_price_state": self.price_state,
            "e2_ret_252d": round(self.ret_252d, 3) if self.ret_252d is not None else None,
            "e2_amt_ratio": round(self.amt_ratio, 2) if self.amt_ratio is not None else None,
        }


class ExpectationV2Shadow:
    """E v2 Shadow 分类器 (只观察不决策)。

    三维:
      Attention: 市场看没看到 (成交额 + 历史涨幅)
      Expectation: 市场相信多少 (历史涨幅代表已交易程度)
      Price State: 当前价格位置 (距高点)
    """

    def __init__(self):
        self._mkt = MarketData()

    def _features(self, code: str, t_date: str) -> dict:
        """PIT 价格特征: 252日涨幅 / 成交比 / 距高点。"""
        df = self._mkt.as_of(code, t_date)
        if df is None or len(df) < 60:
            return {}
        close = df["close"].astype(float)
        amt = df["amount"].dropna().astype(float) if "amount" in df.columns else pd.Series(dtype=float)

        now = float(close.iloc[-1])
        # 过去一年 (~250 交易日)
        win = close.iloc[-250:]
        p0 = float(close.iloc[-251]) if len(close) > 250 else float(close.iloc[0])
        ret_252d = now / p0 - 1 if p0 > 0 else np.nan

        amt_ratio = np.nan
        if len(amt) >= 60:
            cur = float(amt.iloc[-20:].mean())
            hist = float(amt.iloc[-250:].mean()) if len(amt) >= 250 else float(amt.mean())
            amt_ratio = cur / hist if hist > 0 else np.nan

        peak = float(win.max())
        peak_dist = now / peak - 1 if peak > 0 else np.nan
        return {"ret_252d": ret_252d, "amt_ratio": amt_ratio,
                "peak_dist": peak_dist, "now": now}

    def classify(self, code: str, t_date: str,
                 rps: Optional[float] = None) -> ExpectationV2Result:
        f = self._features(code, t_date)
        if not f:
            return ExpectationV2Result(code, "A0", "E0", "PS0", None, None, None,
                                       ["数据不足"])
        ret, ar, pd_ = f["ret_252d"], f["amt_ratio"], f["peak_dist"]
        drivers = [f"252日涨幅{ret:+.0%}", f"成交比{ar:.1f}x", f"距高点{pd_:+.0%}"]

        # ── Attention (市场看没看到) ──
        if ret > 2.0 or (ar is not None and ar > 2.5):
            attn = "A3极热"
        elif ret > 0.5 or (ar is not None and ar > 1.2):
            attn = "A2高关注"
        elif (ar is not None and ar > 0.8) or ret > 0.1:
            attn = "A1初始"
        else:
            attn = "A0未关注"

        # ── Expectation (市场相信多少 = 已交易程度) ──
        if ret > 2.0:
            exp = "E3已透支"
        elif ret > 1.0:
            exp = "E2高预期"
        elif ret > 0.3:
            exp = "E1部分定价"
        else:
            exp = "E0未定价"

        # ── Price State ──
        if pd_ is None:
            ps = "PS0"
        elif pd_ > -0.05:
            ps = "PS0新高区"
        elif pd_ > -0.20:
            ps = "PS1正常"
        elif pd_ > -0.40:
            ps = "PS2回撤"
        else:
            ps = "PS3深度回撤"

        return ExpectationV2Result(code, attn, exp, ps, ret, ar, pd_, drivers)

    def annotate(self, df: pd.DataFrame, t_date: str,
                 rps_map: dict = None) -> pd.DataFrame:
        out = df.copy()
        codes = out["code"].astype(str).str.zfill(6).tolist()
        attns, exps, pss = [], [], []
        for c in codes:
            r = self.classify(c, t_date,
                              rps_map.get(c) if rps_map else None)
            attns.append(r.attention)
            exps.append(r.expectation)
            pss.append(r.price_state)
        out["e2_attention"] = attns
        out["e2_expectation"] = exps
        out["e2_price_state"] = pss
        return out
