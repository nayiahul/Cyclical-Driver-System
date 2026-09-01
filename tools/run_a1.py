"""A1 Baseline: 只修价格 PIT，不恢复乖离/流动性规则（拆分泄漏 vs 功能恢复贡献）

A  (污染)     = 旧系统
A1 (价格PIT)  = 修价格，规则仍失效  → 价格泄漏贡献
B1 (价格+规则) = 修价格 + 规则恢复   → 功能恢复贡献
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# monkeypatch: engine 调用的 apply_valuation_filter 禁用乖离/流动性
import valuation_filter
orig = valuation_filter.apply_valuation_filter
valuation_filter.apply_valuation_filter = (
    lambda t_date, codes, industry_map: orig(t_date, codes, industry_map,
                                             disable_deviation_liquidity=True)
)

from backtest.engine import run_backtest

result = run_backtest(
    "20220101", "20251231",
    use_neutralization=False,
    audit_dir="baseline/a1_price_only/audit",
)
result.nav_series.to_csv("baseline/a1_price_only/nav.csv", header=["nav"])
result.trades.to_csv("baseline/a1_price_only/trades.csv", index=False)
print("A1 done", flush=True)
print(json.dumps(result.stats, default=str, indent=1), flush=True)
