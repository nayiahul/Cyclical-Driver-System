"""Step 8.4-B1: SW 行业指数 Cycle Turning 验证 (徐工型)

问题: 行业指数动量是否提高 L5 恢复质量?

设计 (不改 L5, 只加旁路标签):
  L5 事件 (2022-2025) 按行业指数 3M 动量分组:
    Industry UP:   指数 3M 动量 > 0
    Industry DOWN: 指数 3M 动量 < 0
  检验:
    H1: UP 组恢复率 > DOWN 组恢复率 (周期确认)
    H2: DOWN 组失败率 > UP 组失败率 (过滤假恢复)
    H3: 错误率下降 (UP 组 < L5 v1 基线 8.7%)

样本: 有行业指数覆盖的 L5 事件 (机械/有色/医药/食品/电子/化工/电新/家电)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from loguru import logger

SW_MAP = {
    "机械设备": "sw_index_机械设备", "有色金属": "sw_index_有色金属",
    "医药生物": "sw_index_医药生物", "食品饮料": "sw_index_食品饮料",
    "电子": "sw_index_电子", "基础化工": "sw_index_基础化工",
    "电力设备": "sw_index_电力设备", "家用电器": "sw_index_家用电器",
}


def load_index_momentum(ind_sw1: str, d: str, months: int = 3) -> float | None:
    """行业指数 months 月动量 (PIT: 只用 <=d 数据)。"""
    fname = SW_MAP.get(ind_sw1)
    if not fname:
        return None
    path = f"data/cache/{fname}.csv"
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, parse_dates=["日期"])
    df = df[df["日期"] <= pd.Timestamp(d)].sort_values("日期")
    if len(df) < 30:
        return None
    close = df["收盘"].astype(float)
    # months 月前 (~21 交易日/月)
    lookback = min(len(close) - 1, months * 21)
    p0 = close.iloc[-1 - lookback]
    p1 = close.iloc[-1]
    return float(p1 / p0 - 1) if p0 > 0 else None


def main():
    l5 = pd.read_csv("baseline/l5_recovery_v2.csv")
    l5["code"] = l5["code"].astype(str).str.zfill(6)
    l5["day"] = l5["day"].astype(int)
    sw = pd.read_csv("data/cache/sw_stock_industry.csv", dtype={"code": str})
    ind_map = dict(zip(sw["code"], sw["sw1"]))
    l5["ind"] = l5["code"].map(ind_map)

    # 每事件取指数动量
    rows = []
    for _, ev in l5.iterrows():
        mom = load_index_momentum(ev["ind"], str(ev["day"]))
        if mom is None:
            continue
        rows.append({**ev.to_dict(), "ind_mom_3m": mom})

    df = pd.DataFrame(rows)
    print(f"L5 事件 (有行业指数覆盖): {len(df)} / {len(l5)}")

    df["grp"] = np.where(df["ind_mom_3m"] > 0, "UP", "DOWN")
    print("\n=== Cycle Turning 分组 (SW 指数 3M 动量) ===")
    print(f"{'组':<6}{'n':>6}{'恢复率':>9}{'失败率':>9}{'fwd6':>9}{'Eff':>8}")
    for g in ["UP", "DOWN"]:
        sub = df[df["grp"] == g]
        r2 = sub["R2_state"].dropna()
        f6 = sub["fwd6"].dropna()
        eff = (sub["R2_state"] & sub["R3_excess"]).mean()
        print(f"{g:<6}{len(sub):>6}{r2.mean():>8.1%}{(f6 < -0.2).mean():>8.1%}"
              f"{f6.mean():>8.1%}{eff:>7.1%}")

    base_r2 = df["R2_state"].mean()
    up_r2 = df[df["grp"] == "UP"]["R2_state"].mean()
    dn_r2 = df[df["grp"] == "DOWN"]["R2_state"].mean()
    up_fail = df[df["grp"] == "UP"]["fwd6"].dropna()
    dn_fail = df[df["grp"] == "DOWN"]["fwd6"].dropna()

    print("\n=== H1: UP 恢复率 > DOWN ===")
    print(f"  UP {up_r2:.1%} vs DOWN {dn_r2:.1%} → {'✅' if up_r2 > dn_r2 else '❌'}")
    print("=== H2: DOWN 失败率 > UP ===")
    print(f"  DOWN {(dn_fail < -0.2).mean():.1%} vs UP {(up_fail < -0.2).mean():.1%} → "
          f"{'✅' if (dn_fail < -0.2).mean() > (up_fail < -0.2).mean() else '❌'}")

    # 徐工回放
    for code, name in [("000425", "徐工机械"), ("002192", "融捷股份")]:
        sub = df[df["code"] == code]
        if len(sub):
            r = sub.iloc[0]
            print(f"\n回放 {code} {name}: ind={r['ind']} 指数3M={r['ind_mom_3m']:+.1%} "
                  f"恢复={r['R2_state']} fwd6={r['fwd6']:.0%}")

    df.to_csv("baseline/cycle_turning_audit.csv", index=False)
    print(f"\n已保存 baseline/cycle_turning_audit.csv ({len(df)} 行)")


if __name__ == "__main__":
    main()
