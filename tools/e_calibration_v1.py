"""Step 12-A: E Calibration v1 — Attention 维度验证。

问题: 低 RPS 样本中, "真忽略" vs "高关注回调" 是否可区分?
两类投资含义相反, 后续表现应不同 (验证假设)。

特征 (全部 PIT, 从价格文件构建):
  attn_ret_252d:  过去252日涨幅 (历史热度)
  attn_amt_ratio: 当前20日均成交 / 过去一年日均成交 (当前关注 vs 历史)
  attn_peak_dist: 距过去一年高点距离 (价格位置)
  hist_rps_max:   历史 RPS 峰值 (用采样日近似)

分类 (v2 草案):
  TRUE_IGNORED:   涨幅<50% 且 成交比<1.0 (从未被关注)
  HIGH_ATTN_DROP: 涨幅>100% 且 距高点<-20% (高关注回调)
  ATTN_DROP_SMALL: 其他低RPS

验证: 三类 fwd6 / L1升级率 差异
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

STOCKS = "/Users/nayiahlu/Desktop/stocks"
aud = pd.read_csv("baseline/discovery_audit_2022_2025.csv")
aud["code"] = aud["code"].astype(str).str.zfill(6)
aud["day"] = aud["day"].astype(int)
aud["year"] = aud["day"].astype(str).str[:4]


def price_features(code: str, day: int) -> dict:
    """PIT: 只用 <= day 的价格算历史特征。"""
    path = f"{STOCKS}/{code}.csv"
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, dtype={"date": str})
    df["date"] = df["date"].str.replace("-", "")
    df = df[df["date"] <= str(day)].sort_values("date")
    if len(df) < 60:
        return {}
    close = df["close"].astype(float)
    amt = df["amount"].astype(float) if "amount" in df.columns else pd.Series(dtype=float)

    now = float(close.iloc[-1])
    # 过去一年窗口
    win = df[df["date"] >= str(day - 10000)] if len(df) > 250 else df  # 约一年
    if len(win) < 60:
        win = df
    # 1. 252日涨幅 (从过去一年起点)
    p0 = float(win["close"].iloc[0])
    ret_252 = now / p0 - 1 if p0 > 0 else np.nan
    # 2. 成交比: 当前20日 vs 过去一年
    if len(amt) > 40:
        cur_amt = float(amt.iloc[-20:].mean())
        hist_amt = float(amt.iloc[-260:].mean()) if len(amt) >= 260 else float(amt.mean())
        amt_ratio = cur_amt / hist_amt if hist_amt > 0 else np.nan
    else:
        amt_ratio = np.nan
    # 3. 距高点
    peak = float(win["close"].max())
    dist = now / peak - 1 if peak > 0 else np.nan
    return {"ret_252d": ret_252, "amt_ratio": amt_ratio, "peak_dist": dist}


def main():
    # 低 RPS 样本 (原 E0/E1 区: 系统认为"市场未确认")
    low = aud[(aud["rps"] < 50)].dropna(subset=["fwd6"]).copy()
    # 采样控制 (性能): 每采样日最多 150 只
    sel = low.groupby("day", group_keys=False).apply(
        lambda x: x.sample(min(150, len(x)), random_state=42)).reset_index(drop=True)
    print(f"低RPS样本采样: {len(sel)}")

    # 逐只算特征
    feats = []
    for _, r in sel.iterrows():
        f = price_features(r["code"], int(r["day"]))
        if f:
            f.update({"code": r["code"], "day": r["day"],
                      "fwd6": r["fwd6"], "discovery": r["discovery"],
                      "year": r["year"]})
            feats.append(f)
    df = pd.DataFrame(feats)
    print(f"有价格特征: {len(df)}")

    # 分类 v2
    df["cat"] = "OTHER"
    df.loc[(df["ret_252d"] < 0.5) & (df["amt_ratio"] < 1.0), "cat"] = "TRUE_IGNORED"
    df.loc[(df["ret_252d"] > 1.0) & (df["peak_dist"] < -0.2), "cat"] = "HIGH_ATTN_DROP"
    df.loc[(df["ret_252d"] > 1.0) & (df["peak_dist"] >= -0.2), "cat"] = "HIGH_ATTN_STRONG"

    print("\n=== 分类分布 ===")
    print(df["cat"].value_counts().to_string())

    print("\n=== 各类 fwd6 (核心验证) ===")
    for c in ["TRUE_IGNORED", "HIGH_ATTN_DROP", "HIGH_ATTN_STRONG", "OTHER"]:
        g = df[df["cat"] == c]
        if len(g):
            print(f"  {c:<18} n={len(g):>5} fwd6={g['fwd6'].mean():>7.1%} "
                  f"失败率={(g['fwd6']<-0.2).mean():>6.1%}")

    # 按 discovery 强弱再分 (L1 候选内)
    print("\n=== 强变化内 (discovery>=0.5, 即原 L1 候选) ===")
    strong = df[df["discovery"] >= 0.5]
    for c in ["TRUE_IGNORED", "HIGH_ATTN_DROP", "OTHER"]:
        g = strong[strong["cat"] == c]
        if len(g):
            print(f"  {c:<18} n={len(g):>5} fwd6={g['fwd6'].mean():>7.1%}")

    # 大牛股回撤检测 (用户举例)
    print("\n=== 大牛股回撤检测 (2025年采样点) ===")
    for code, name in [("300308", "中际旭创"), ("300502", "新易盛"), ("002463", "沪电")]:
        sub = df[(df["code"] == code)]
        if len(sub):
            r = sub.iloc[-1]
            print(f"  {code} {name}: ret_252d={r['ret_252d']:+.0%} amt_ratio={r['amt_ratio']:.1f}x "
                  f"peak_dist={r['peak_dist']:+.0%} → 分类={r['cat']}")

    df.to_csv("baseline/e_calibration_v1.csv", index=False)
    print(f"\n已保存 baseline/e_calibration_v1.csv ({len(df)} 行)")


if __name__ == "__main__":
    main()
