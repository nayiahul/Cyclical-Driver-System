"""Brinson 归因 — 拆解超额收益来源

配置效应: Σ (w_pi - w_bi) × r_bi    → 超配了正确的行业吗？
选择效应: Σ w_bi × (r_pi - r_bi)      → 在行业内选了正确的股票吗？
交互效应: Σ (w_pi - w_bi) × (r_pi - r_bi) → 交叉项

基准: 全A股等权（universe 内所有股票等权分配）
"""
from collections import defaultdict

import numpy as np
import pandas as pd


class BrinsonAttributor:
    """累积 Brinson 归因，每期追加，最终汇总。"""

    def __init__(self):
        self.records: list[dict] = []

    def record(self, date: str,
               holdings: dict[str, float],   # {code: shares}
               prices: dict[str, float],      # {code: current_price}
               prices_prev: dict[str, float], # {code: price_at_last_rebalance}
               industry_map: dict[str, str],  # {code: industry}
               universe_codes: list[str],     # all eligible codes
               ):
        """记录一期的归因数据。

        holdings/prices: 当前调仓日的持仓和价格
        prices_prev: 上期调仓日的价格（用于计算区间收益）
        """
        if not holdings or not prices_prev:
            return

        # 组合当前市值
        port_value = sum(holdings.get(c, 0) * prices.get(c, 0)
                        for c in set(list(holdings) + list(prices_prev))
                        if prices.get(c, 0) > 0)
        if port_value == 0:
            return

        # --- 组合: 行业权重与收益 ---
        port_ind_value = defaultdict(float)
        port_ind_prev_value = defaultdict(float)
        for code, shares in holdings.items():
            ind = industry_map.get(code, "未知")
            p = prices.get(code, 0)
            pp = prices_prev.get(code, 0)
            if p > 0:
                port_ind_value[ind] += shares * p
            if pp > 0:
                port_ind_prev_value[ind] += shares * pp

        port_ind_weight = {ind: val / port_value
                          for ind, val in port_ind_value.items()}

        # 组合行业收益 (简单: 持仓加权)
        port_ind_return = {}
        for ind in port_ind_prev_value:
            prev_v = port_ind_prev_value[ind]
            curr_v = port_ind_value.get(ind, 0)
            # 考虑调仓导致的权重变化: 用上期权重 × 行业个股等权收益近似
            # 简化: 直接比较期末期初价值
            if prev_v > 0:
                port_ind_return[ind] = curr_v / prev_v - 1

        # --- 基准: 全A等权行业收益 ---
        bench_ind_ret = defaultdict(list)
        bench_ind_weight = defaultdict(float)
        total_weight = 0
        for code in universe_codes:
            ind = industry_map.get(code, "未知")
            cp = prices.get(code, 0)
            pp = prices_prev.get(code, 0)
            if cp > 0 and pp > 0:
                bench_ind_ret[ind].append(cp / pp - 1)
                bench_ind_weight[ind] += 1  # equal weight: each stock counts as 1
                total_weight += 1

        # 基准行业等权收益
        bench_ind_avg_ret = {ind: np.mean(rets) if rets else 0
                            for ind, rets in bench_ind_ret.items()}
        # 基准行业权重
        bench_ind_w = {ind: w / total_weight if total_weight > 0 else 0
                      for ind, w in bench_ind_weight.items()}

        # --- Brinson 分解 ---
        alloc_effect = 0.0
        select_effect = 0.0
        interact_effect = 0.0

        all_inds = set(list(bench_ind_w) + list(port_ind_weight))
        for ind in all_inds:
            wp = port_ind_weight.get(ind, 0)
            wb = bench_ind_w.get(ind, 0)
            rp = port_ind_return.get(ind, 0)
            rb = bench_ind_avg_ret.get(ind, 0)

            alloc_effect += (wp - wb) * rb
            select_effect += wb * (rp - rb)
            interact_effect += (wp - wb) * (rp - rb)

        self.records.append({
            "date": date,
            "alloc_effect": alloc_effect,
            "select_effect": select_effect,
            "interact_effect": interact_effect,
            "total_excess": alloc_effect + select_effect + interact_effect,
        })

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.records)

    def summary(self) -> dict:
        """返回累积归因汇总。"""
        df = self.to_dataframe()
        if df.empty:
            return {}
        total = df[["alloc_effect", "select_effect", "interact_effect"]].sum()
        total_abs = total.abs().sum()
        if total_abs == 0:
            return {}
        return {
            "cum_alloc": total["alloc_effect"],
            "cum_select": total["select_effect"],
            "cum_interact": total["interact_effect"],
            "cum_total": total.sum(),
            "alloc_pct": total["alloc_effect"] / total.sum() * 100 if total.sum() != 0 else 0,
            "select_pct": total["select_effect"] / total.sum() * 100 if total.sum() != 0 else 0,
            "interact_pct": total["interact_effect"] / total.sum() * 100 if total.sum() != 0 else 0,
            "n_periods": len(df),
        }
