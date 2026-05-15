import os
from backtest.engine import run_backtest

result = run_backtest('20150101', '20241231')
stats = result.stats

print()
print('=== Slice 4 (正交+IR权重+排雷) ===')
for k, v in stats.items(): 
    print(f'  {k}: {v}')

os.makedirs('output', exist_ok=True)
result.nav_series.to_csv('output/nav_slice4.csv', header=['nav'])
result.trades.to_csv('output/trades_slice4.csv', index=False)
print()
print('已保存至 output/nav_slice4.csv')
