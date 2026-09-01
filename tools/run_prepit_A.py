"""Gate 0-D: PRE-PIT Baseline A — 当前代码(commit b47e4c0) + 当前数据, PIT 未修复"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest.engine import run_backtest

AUDIT_DIR = "baseline/pre_pit_A/audit"
result = run_backtest(
    "20220101", "20251231",
    use_neutralization=False,
    audit_dir=AUDIT_DIR,
)
result.nav_series.to_csv("baseline/pre_pit_A/nav.csv", header=["nav"])
result.trades.to_csv("baseline/pre_pit_A/trades.csv", index=False)
print("PRE-PIT A done", flush=True)
print(json.dumps(result.stats, default=str, indent=1), flush=True)
