"""生命周期判定 + 动态权重。

classify_lifecycle(code, t_date) 判定四阶段。
"""
import pandas as pd
import numpy as np
from typing import Tuple, Optional
from loguru import logger

from growth_os.config import (
    LifecycleStage, LIFECYCLE_RULES, WEIGHT_MATRIX, COMMODITY_INDUSTRIES,
)
from growth_os.data import (
    get_quarterly_series, get_financial_snapshot, load_tdx_financials, get_industry,
    compute_revenue_cagr_3y, compute_roic_ttm,
)
from growth_os.wacc import compute_wacc

# 全局追踪器 {code: LifecycleTracker}
_trackers: dict = {}

# 锁定期：2个财报期（≈半年）
LOCK_PERIODS = 2


class LifecycleTracker:
    """跨期生命周期追踪器，带锁定期防抖。

    核心逻辑：
    - 新判定需要连续2期确认才生效
    - 锁定期内用旧阶段，可选混合权重过渡
    """

    def __init__(self, code: str):
        self.code = code
        self.current_stage: LifecycleStage | None = None
        self.pending_stage: LifecycleStage | None = None
        self.pending_count = 0          # 连续偏离当前阶段的期数
        self.stage_scores: dict = {}    # {stage: probability}

    def update(self, raw_stage: LifecycleStage) -> LifecycleStage:
        """输入原始分类，返回锁定后的阶段。"""
        if self.current_stage is None:
            self.current_stage = raw_stage
            self.pending_count = 0
            return self.current_stage

        if raw_stage == self.current_stage:
            self.pending_count = 0
            self.pending_stage = None
            return self.current_stage

        # 偏离当前阶段
        if self.pending_stage == raw_stage:
            self.pending_count += 1
        else:
            self.pending_stage = raw_stage
            self.pending_count = 1

        # 连续偏离满 LOCK_PERIODS → 切换
        if self.pending_count >= LOCK_PERIODS:
            self.current_stage = self.pending_stage
            self.pending_stage = None
            self.pending_count = 0

        return self.current_stage

    def get_mixed_weights(self, raw_stage: LifecycleStage) -> dict:
        """输出混合权重。

        正常期：纯当前阶段权重
        过渡期（pending但未满锁定期）：新旧权重线性混合
        """
        current_w = WEIGHT_MATRIX.get(self.current_stage)
        if current_w is None:
            return None

        if self.pending_stage is None or self.pending_count == 0:
            return dict(current_w)

        pending_w = WEIGHT_MATRIX.get(self.pending_stage)
        if pending_w is None:
            return dict(current_w)

        # 过渡混合：pending_count / LOCK_PERIODS 的比例用新权重
        alpha = min(self.pending_count / LOCK_PERIODS, 1.0)
        mixed = {}
        for key in current_w:
            mixed[key] = current_w[key] * (1 - alpha) + pending_w[key] * alpha
        return mixed


def get_tracker(code: str) -> LifecycleTracker:
    """获取或创建 lifecycle tracker。"""
    if code not in _trackers:
        _trackers[code] = LifecycleTracker(code)
    return _trackers[code]


def resolve_weights(code: str, raw_stage: LifecycleStage) -> dict | None:
    """统一入口：输入 code + 原始阶段 → 输出锁定后的混合权重。

    替换直接调用 get_weights(stage)。
    """
    if raw_stage == LifecycleStage.DECLINE:
        return None  # 衰退期无权重，走观察池

    tracker = get_tracker(code)
    locked_stage = tracker.update(raw_stage)
    return tracker.get_mixed_weights(raw_stage)


def _get_latest_fy_roic(code: str, t_date: str) -> float | None:
    """获取最近一个完整财年的ROIC。

    当处于Q1/H1/9M时，ROIC因NOPAT累计不足而偏低，
    此时用最近1231报告期的ROIC替代更合理。
    """
    roic_series = get_quarterly_series(code, "roic", n_quarters=8, t_date=t_date)
    if len(roic_series) < 2:
        return None
    # 找最近一个1231报告期
    fy_indices = [i for i, d in enumerate(roic_series.index) if str(d).endswith("1231")]
    if fy_indices:
        fy_roic = roic_series.iloc[fy_indices[-1]]
        if not pd.isna(fy_roic):
            return float(fy_roic)
    return None


def _get_expense_ratio_delta(ratio_series) -> float | None:
    """计算费用率近4季 vs 前4季的变化（pp），用于判断是否组织扩张。"""
    clean = ratio_series.dropna()
    if len(clean) < 6:
        return None
    recent = clean.iloc[-4:].mean()
    prior = clean.iloc[-8:-4].mean() if len(clean) >= 8 else clean.iloc[:4].mean()
    return round(recent - prior, 1)


def classify_lifecycle(
    code: str, t_date: str, industry_l3: str = None
) -> Tuple[LifecycleStage, str]:
    """判定生命周期阶段。

    Returns:
        (stage, reason)
    """
    if industry_l3 is None:
        industry_l3 = get_industry(code)

    # P1-2: 商品行业预检 — 营收高增若来自价格而非组织扩张，不应标为加速期
    is_commodity = any(kw in (industry_l3 or "") for kw in COMMODITY_INDUSTRIES)

    snap = get_financial_snapshot(t_date)
    row = snap[snap["code"] == code]
    if row.empty:
        return LifecycleStage.DECLINE, "无财务数据"
    row = row.iloc[0]

    # --- 收集信号 ---
    revenue = row.get("revenue", 0) or 0
    revenue_yoy = row.get("revenue_yoy")
    deducted_yoy = row.get("deducted_profit_yoy")
    deducted_q = row.get("deducted_profit_q") or 0
    gross_margin = row.get("gross_margin")
    roic_raw = row.get("roic")
    roic_ttm = compute_roic_ttm(code, t_date)
    roic = roic_ttm if roic_ttm is not None else roic_raw
    net_margin = row.get("net_margin")
    fcf = row.get("fcff_per_share")
    ocf_to_profit = row.get("ocf_to_profit")

    # 季度序列
    gm_series = get_quarterly_series(code, "gross_margin", n_quarters=12, t_date=t_date)
    roic_series = get_quarterly_series(code, "roic", n_quarters=12, t_date=t_date)
    rev_yoy_series = get_quarterly_series(code, "revenue_yoy", n_quarters=12, t_date=t_date)

    # --- 衰退判定 ---
    wacc = compute_wacc(code, t_date)

    # ROIC口径: 优先TTM(compute_roic_ttm)，回退快照值
    roic_below_wacc = False
    if roic is not None and wacc is not None and not pd.isna(roic):
        roic_below_wacc = roic < wacc

    # 毛利率连续2季实质下滑(每季降幅>1pp 或累计>3pp)
    gm_decline = False
    if len(gm_series) >= 4:
        recent_gm = gm_series.iloc[-4:].dropna()
        if len(recent_gm) >= 3:
            q1, q2, q3 = recent_gm.iloc[-3], recent_gm.iloc[-2], recent_gm.iloc[-1]
            decline_q2 = q2 < q1 - 1.0
            decline_q3 = q3 < q2 - 1.0
            total_decline = q1 - q3
            gm_decline = (decline_q2 and decline_q3) or total_decline > 3.0

    # 应收/存货异常
    notes_recv = row.get("notes_and_acct_receivable")
    inventory = row.get("inventory")
    recv_surge = False
    inv_surge = False
    if notes_recv and revenue > 0 and revenue_yoy:
        # 简单检测: 应收增速 vs 营收增速
        recv_growth_q = get_quarterly_series(code, "notes_and_acct_receivable",
                                             n_quarters=4, t_date=t_date)
        if len(recv_growth_q.dropna()) >= 2:
            recv_prev = recv_growth_q.iloc[-2] if len(recv_growth_q) >= 2 else recv_growth_q.iloc[-1]
            if recv_prev > 0:
                recv_surge = (recv_growth_q.iloc[-1] / recv_prev - 1) > 0.5

    # 费用率恶化
    expense_ratio_worse = False
    admin_ratio_series = get_quarterly_series(code, "admin_expense_ratio",
                                              n_quarters=6, t_date=t_date)
    if len(admin_ratio_series.dropna()) >= 3:
        recent = admin_ratio_series.iloc[-3:].dropna()
        if len(recent) >= 3:
            expense_ratio_worse = (recent.iloc[-1] > recent.iloc[-3])

    # 衰退期需要强信号: 毛利率实质下滑 + 至少一个其他恶化信号
    # 仅有ROIC<WACC不足够(重资本行业投入期ROIC可暂时低于WACC)
    decline_signals = []
    if gm_decline:
        decline_signals.append("毛利率连续下滑")
    if recv_surge:
        decline_signals.append("应收异常")
    if inv_surge:
        decline_signals.append("存货异常")

    if len(decline_signals) >= 2:
        return LifecycleStage.DECLINE, " + ".join(decline_signals)

    # ROIC<WACC 只在同时有营收萎缩和费用率恶化时才视为衰退
    if (roic_below_wacc and expense_ratio_worse
            and revenue_yoy is not None and not pd.isna(revenue_yoy)
            and revenue_yoy < -5):
        return LifecycleStage.DECLINE, f"ROIC({roic:.1f}%)<WACC + 费用恶化 + 营收负增{revenue_yoy:.1f}%"

    # --- 导入期判定 ---
    # 汽车/制造业净利率2-3%正常，阈值降到1%避免误杀
    is_unprofitable = (deducted_q < 0 or
                       (net_margin is not None and not pd.isna(net_margin) and net_margin < 1))

    if revenue > 0 and is_unprofitable:
        # 还需营收增速高于行业
        if revenue_yoy is not None and not pd.isna(revenue_yoy) and revenue_yoy > 0:
            return LifecycleStage.INTRODUCTION, (
                f"营收为正但利润微薄/为负(净利率{net_margin:.1f}%)")
        else:
            return LifecycleStage.DECLINE, "营收不增长且亏损"

    # --- 商品行业脉冲检测（P1-2） ---
    # 商品驱动的利润增长 vs 内生飞轮成长：真成长伴随组织扩张（费用率上升）
    if is_commodity:
        rev_yoy_val = revenue_yoy if revenue_yoy is not None and not pd.isna(revenue_yoy) else 0
        if rev_yoy_val > 30:
            # 检查费用率是否同步扩张（真成长的特征 = 规模扩张 = 费用率上升）
            admin_delta = _get_expense_ratio_delta(admin_ratio_series)
            if admin_delta is not None and admin_delta < 2:
                return LifecycleStage.MATURITY, (
                    f"商品价格脉冲(营收+{rev_yoy_val:.0f}%但费用率仅+{admin_delta:.1f}pp→非组织扩张)")
            else:
                return LifecycleStage.MATURITY, (
                    f"资源股商品周期(营收+{rev_yoy_val:.0f}%，毛利率{gross_margin:.0f}%)")
        else:
            # 商品行业营收增速不突出→成熟期
            return LifecycleStage.MATURITY, (
                f"资源股平稳期(营收+{rev_yoy_val:.0f}%，毛利率{gross_margin:.0f}%)")

    # --- 加速期判定 ---
    # 营收3年CAGR: 用绝对营收TTM计算
    cagr_3y = compute_revenue_cagr_3y(code, t_date)
    if cagr_3y is None:
        cagr_3y = revenue_yoy if revenue_yoy is not None and not pd.isna(revenue_yoy) else 0

    # 扣非增速 >= 营收增速
    deducted_vs_revenue = (deducted_yoy is not None and revenue_yoy is not None
                           and not pd.isna(deducted_yoy) and not pd.isna(revenue_yoy)
                           and deducted_yoy >= revenue_yoy * 0.8)

    # 毛利率不降
    gm_stable_or_up = True
    if len(gm_series) >= 8:
        recent_gm = gm_series.iloc[-4:].mean()
        old_gm = gm_series.iloc[-8:-4].mean()
        gm_stable_or_up = recent_gm >= old_gm * 0.98  # 允许2%内波动

    # ROIC提升
    roic_up = False
    if len(roic_series) >= 8:
        recent_roic = roic_series.iloc[-4:].mean()
        old_roic = roic_series.iloc[-8:-4].mean()
        roic_up = not pd.isna(recent_roic) and not pd.isna(old_roic) and recent_roic > old_roic

    rules = LIFECYCLE_RULES["acceleration"]
    if (cagr_3y >= rules["min_revenue_cagr_3y"]
            and deducted_vs_revenue
            and gm_stable_or_up):
        return LifecycleStage.ACCELERATION, (
            f"营收CAGR{cagr_3y:.1f}% + 扣非增速同步 + 毛利率稳定 + ROIC{'提升' if roic_up else '平稳'}")

    # --- 成熟期判定 ---
    if roic is not None and wacc is not None and roic > wacc:
        fcf_ok = fcf is not None and not pd.isna(fcf) and fcf > 0
        rev_growth = revenue_yoy if revenue_yoy is not None and not pd.isna(revenue_yoy) else 0
        if rev_growth > 0 and fcf_ok:
            return LifecycleStage.MATURITY, (
                f"ROIC({roic:.1f}%)>WACC({wacc:.1f}%) + FCF为正 + 增速放缓至{rev_growth:.1f}%")

    # --- 默认：加速期 ---
    if cagr_3y >= 10 and deducted_vs_revenue:
        return LifecycleStage.ACCELERATION, f"营收CAGR{cagr_3y:.1f}%(低于15%但增长健康)"
    elif not is_unprofitable and revenue > 0:
        return LifecycleStage.MATURITY, "利润为正但未达加速标准"
    else:
        return LifecycleStage.DECLINE, "无匹配阶段"


def get_weights(stage: LifecycleStage) -> dict | None:
    """获取生命周期的动态权重。"""
    return WEIGHT_MATRIX.get(stage)
