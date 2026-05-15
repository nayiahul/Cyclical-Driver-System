# Slice 4 参数网格扫描 设计文档

**日期**: 2026-05-16
**基于**: Slice 4（正交+IR+排雷，17.76% 年化，夏普 0.50）
**目标**: 扫描 TOP_N 和 PEG 阈值的最优组合，验证能否超越当前基准

---

## 1. 参数化

### 1.1 config/params.py 新增

```python
PEG_MAX = 2.5  # 估值排雷 PEG上限
```

### 1.2 valuation_filter.py 修改

PEG 判定从硬编码改为 `from config.params import PEG_MAX`。

## 2. 扫描矩阵

| 参数 | 值 | 含义 |
|------|-----|------|
| TOP_N_STOCKS | 50, 100, 150 | 选股数量 |
| PEG_MAX | 2.0, 2.5, 3.0 | PEG剔除阈值（越低越严格） |

3 × 3 = 9 组。基准 = (100, 2.5)，即 Slice 4 已跑过的组合。

## 3. param_sweep.py

```python
sweep.py:
  for top_n in [50, 100, 150]:
    for peg in [2.0, 2.5, 3.0]:
      修改 config.TOP_N_STOCKS / config.PEG_MAX
      重新加载估值排雷模块
      result = run_backtest()
      记录到 sweep_results.csv
      print 进度
```

不缓存中间数据（每一组独立跑完整回测）。

## 4. 输出

`output/sweep_results.csv`：

```
top_n,peg,annual_return,sharpe,max_drawdown,total_return,volatility,win_rate
50,2.0,...
...
```

每组跑完立即追加一行，方便中途查看进度。

## 5. 成功标准

- [ ] 9 组全部完成，无异常中断
- [ ] 最优组合夏普 > 当前基准（0.50 为优秀，持平也可接受）
- [ ] 最优组合最大回撤不显著恶化（< -60%）
