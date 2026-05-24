#!/usr/bin/env python3
"""批量筛选脚本 — 全市场扫描输出 Top N CSV。"""
import os, sys, time, warnings
import pandas as pd
import numpy as np
warnings.filterwarnings('ignore')

from growth_os.data import load_growth_data, get_industry
from growth_os.lifecycle import classify_lifecycle
from growth_os.funnel import run_funnel
from growth_os.scorecard import GrowthScorecard, compute_composite


def main():
    t_date = sys.argv[1] if len(sys.argv) > 1 else "20260331"
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    min_cap = float(sys.argv[3]) if len(sys.argv) > 3 else 50
    pool_size = int(sys.argv[4]) if len(sys.argv) > 4 else 500

    print(f"日期: {t_date} | Top: {top_n} | 市值>{min_cap}亿 | 候选池: {pool_size}只")
    t_start = time.time()

    # 加载
    df = load_growth_data(t_date)
    df = df[df['market_cap'] >= min_cap].nlargest(pool_size, 'market_cap')
    codes = df['code'].tolist()
    names = dict(zip(df['code'], df['code']))
    print(f"候选池: {len(codes)} 只 | 预计 {len(codes)*3/60:.0f} 分钟")

    # 逐只打分
    rows = []
    for i, code in enumerate(codes):
        if (i + 1) % 100 == 0:
            elapsed = time.time() - t_start
            eta = elapsed / (i + 1) * (len(codes) - i - 1) / 60
            print(f"  {i+1}/{len(codes)} ({elapsed:.0f}s, ETA {eta:.0f}min)")

        try:
            ind = get_industry(code)
            lc, lc_reason = classify_lifecycle(code, t_date, ind)
            funnel = run_funnel(code, t_date, ind, lc)
            card = GrowthScorecard(
                code=code, name=names.get(code, code),
                industry_l3=ind, industry_l1="",
                lifecycle=lc, lifecycle_reason=lc_reason,
                pass_l1=funnel['pass_l1'],
                l1_red_flags=funnel['l1_red_flags'],
                score_l2=funnel.get('score_l2', np.nan),
                score_l3=funnel.get('score_l3', np.nan),
                score_l4=funnel.get('score_l4', np.nan),
                score_l5=funnel.get('score_l5', np.nan),
            )
            card = compute_composite(card, funnel)
            rows.append(card.to_dict())
        except Exception as e:
            continue

    # 排序输出
    df_out = pd.DataFrame(rows)
    if len(df_out) == 0:
        print("无有效结果")
        return

    df_out = df_out.sort_values('composite_score', ascending=False).head(top_n)

    os.makedirs('output', exist_ok=True)
    out_path = f'output/growth_pool_top{top_n}_{t_date}.csv'
    df_out.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"\n已保存: {out_path}")

    # 摘要
    print(f"\n{'='*80}")
    print(f"  Top {top_n} 摘要")
    print(f"{'='*80}")
    cols_show = ['code','industry_l3','lifecycle','composite_score','score_l2','score_l3','score_l4','score_l5','decision']
    for _, r in df_out.head(top_n).iterrows():
        print(f"  {r['code']} {str(r['industry_l3'])[:18]:18s} {r['lifecycle']:6s} "
              f"综合={r['composite_score']:5.0f} L2={r['score_l2']:4.1f} "
              f"L3={r['score_l3']:4.1f} L4={r['score_l4']:4.1f} L5={r['score_l5']:4.1f} {r['decision']}")

    # 总统计
    df_all = pd.DataFrame(rows)
    stages = df_all['lifecycle'].value_counts().to_dict()
    decisions = df_all['decision'].value_counts().to_dict()
    l1_pass = df_all['pass_l1'].sum()
    print(f"\n全池 ({len(df_all)}只):")
    print(f"  L1通关: {l1_pass}/{len(df_all)} ({l1_pass/len(df_all)*100:.0f}%)")
    print(f"  阶段: {stages}")
    print(f"  决策: {decisions}")
    print(f"  Top{top_n}平均分: {df_out['composite_score'].mean():.0f}")
    print(f"  耗时: {(time.time()-t_start)/60:.1f} 分钟")


if __name__ == '__main__':
    main()
