"""周期驱动因子系统 — 主入口"""
import os

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

    print(f"\n年化收益: {stats.get('annual_return', 0):.2%}")
    print(f"年化波动: {stats.get('annual_volatility', 0):.2%}")
    print(f"夏普比率: {stats.get('sharpe_ratio', 0):.2f}")
    print(f"最大回撤: {stats.get('max_drawdown', 0):.2%}")


if __name__ == "__main__":
    main()
