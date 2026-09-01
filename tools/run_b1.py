"""B1 Baseline: Gate 3 后（价格 PIT + 乖离/流动性恢复），财务 PIT 未修"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest.engine import run_backtest

result = run_backtest(
    "20220101", "20251231",
    use_neutralization=False,
    audit_dir="baseline/b1_price_pit/audit",
)
result.nav_series.to_csv("baseline/b1_price_pit/nav.csv", header=["nav"])
result.trades.to_csv("baseline/b1_price_pit/trades.csv", index=False)
print("B1 done", flush=True)
print(json.dumps(result.stats, default=str, indent=1), flush=True)
