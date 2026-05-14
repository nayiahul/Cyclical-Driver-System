"""周期驱动因子系统 — 主入口"""
import os

import pandas as pd

from backtest.engine import run_backtest
from config.params import OUTPUT_DIR


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    result = run_backtest("20150101", "20241231")

    stats = result.stats
    print("\n=== 回测统计 ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    nav_path = os.path.join(OUTPUT_DIR, "nav.csv")
    result.nav_series.to_csv(nav_path, header=["nav"])
    print(f"\n净值序列已保存至 {nav_path}")

    trades_path = os.path.join(OUTPUT_DIR, "trades.csv")
    result.trades.to_csv(trades_path, index=False)
    print(f"交易记录已保存至 {trades_path}")

    print(f"\n年化收益: {stats['annual_return']:.2%}")
    print(f"年化波动: {stats['annual_volatility']:.2%}")
    print(f"夏普比率: {stats['sharpe_ratio']:.2f}")
    print(f"最大回撤: {stats['max_drawdown']:.2%}")


if __name__ == "__main__":
    main()
