import os
from backtest.engine import run_backtest

result = run_backtest('20220101', '20251231')
stats = result.stats

print()
print('=== Slice 5 (风险中性化+周期IR) ===')
for k, v in stats.items():
    print(f'  {k}: {v}')

os.makedirs('output', exist_ok=True)
result.nav_series.to_csv('output/nav_slice5.csv', header=['nav'])
result.trades.to_csv('output/trades_slice5.csv', index=False)
print()
print('已保存至 output/nav_slice5.csv')
