"""B Baseline: 完整 PIT（Gate 2-4 全部完成）— 价格 + 财务 + 规则恢复"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest.engine import run_backtest

result = run_backtest(
    "20220101", "20251231",
    use_neutralization=False,
    audit_dir="baseline/b_full_pit/audit",
)
result.nav_series.to_csv("baseline/b_full_pit/nav.csv", header=["nav"])
result.trades.to_csv("baseline/b_full_pit/trades.csv", index=False)
print("B done", flush=True)
print(json.dumps(result.stats, default=str, indent=1), flush=True)
