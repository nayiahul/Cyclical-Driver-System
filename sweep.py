"""参数网格扫描 — TOP_N × PEG_MAX"""
import importlib
import os
import sys
import time

import config.params as cfg
from backtest.engine import run_backtest

# 扫描矩阵
TOP_N_LIST = [50, 100, 150]
PEG_LIST = [2.0, 2.5, 3.0]
TOTAL = len(TOP_N_LIST) * len(PEG_LIST)

os.makedirs("output", exist_ok=True)
out_path = "output/sweep_results.csv"

# 写入表头
with open(out_path, "w") as f:
    f.write("top_n,peg,annual_return,sharpe,max_drawdown,total_return,volatility,win_rate\n")

n = 0
for top_n in TOP_N_LIST:
    for peg in PEG_LIST:
        n += 1
        print(f"\n{'='*60}")
        print(f"[{n}/{TOTAL}] TOP_N={top_n}, PEG_MAX={peg}")
        print(f"{'='*60}")

        # 修改参数
        cfg.TOP_N_STOCKS = top_n
        cfg.PEG_MAX = peg

        # 重新加载依赖模块（强制应用新参数）
        import valuation_filter
        import signals
        importlib.reload(valuation_filter)
        importlib.reload(signals)
        import backtest.engine
        importlib.reload(backtest.engine)

        t0 = time.time()
        try:
            result = backtest.engine.run_backtest("20150101", "20241231")
            stats = result.stats
            elapsed = (time.time() - t0) / 60

            with open(out_path, "a") as f:
                f.write(f"{top_n},{peg},{stats['annual_return']},{stats['sharpe_ratio']},"
                        f"{stats['max_drawdown']},{stats['total_return']},"
                        f"{stats['annual_volatility']},{stats['win_rate']}\n")

            print(f"  年化: {stats['annual_return']:.2%}  夏普: {stats['sharpe_ratio']:.2f}  "
                  f"回撤: {stats['max_drawdown']:.2%}  耗时: {elapsed:.0f}min")
        except Exception as e:
            print(f"  FAILED: {e}")
            with open(out_path, "a") as f:
                f.write(f"{top_n},{peg},ERROR,{e},,,,\n")

print(f"\n{'='*60}")
print(f"扫描完成。结果: {out_path}")
print(f"{'='*60}")
