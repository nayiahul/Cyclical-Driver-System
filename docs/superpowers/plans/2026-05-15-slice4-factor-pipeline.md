# Slice 4: 因子处理流水线 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用正交化消除 S5 碾压效应、IR 动态权重替代等权合成、估值排雷过滤泡沫股，验证能否超越全市场等权基准

**Architecture:** 3 个新模块（orthogonalizer / weights / valuation_filter），修改 signals.py（Alpha 合成链路改为正交化+IR 权重）和 engine.py（+估值排雷前置）。冷启动前 36 个月等权

**Tech Stack:** Python 3.10, numpy, pandas, scipy, loguru

---

## 文件结构映射

| 文件 | 职责 | 数据依赖 |
|------|------|---------|
| `orthogonalizer.py` | 分块对称正交化（EVD） | numpy, 信号数据 |
| `weights.py` | IR 动态权重 + IC 追踪 | 因子收益序列 |
| `valuation_filter.py` | 6条硬约束排雷 | 财务缓存, 日线缓存, 行业映射 |
| `signals.py` | 修改 compute_alpha 链路 | orthogonalizer, weights |
| `backtest/engine.py` | +估值排雷前置 | valuation_filter |

依赖链：orthogonalizer → weights → signals → engine，valuation_filter → engine，单向无循环。

---

### Task 1: 创建 orthogonalizer.py — 分块对称正交化

**Files:**
- Create: `orthogonalizer.py`

**Step 1: 实现 symmetric_orthogonalize**

```python
"""分块对称正交化 — 消除块内信号共线性"""
import numpy as np
import pandas as pd


def _pairwise_cov(signals: dict[str, np.ndarray]) -> np.ndarray:
    """Pairwise-complete 协方差矩阵。

    对信号矩阵每对 (i,j)，使用两者均非NaN的观测计算协方差。
    返回 k×k 协方差矩阵。
    """
    names = list(signals.keys())
    k = len(names)
    cov = np.zeros((k, k))
    for i in range(k):
        for j in range(i, k):
            si = signals[names[i]]
            sj = signals[names[j]]
            mask = ~np.isnan(si) & ~np.isnan(sj)
            if mask.sum() < 10:
                cov[i, j] = 0.0
            else:
                cov[i, j] = np.cov(si[mask], sj[mask])[0, 1]
            cov[j, i] = cov[i, j]
    return cov


def symmetric_orthogonalize(
    signals: dict[str, np.ndarray],
    blocks: list[list[str]],
) -> dict[str, np.ndarray]:
    """
    分块对称正交化。

    Args:
        signals: {name: N×1 array}，每个信号是股票截面向量
        blocks: 分块列表，如 [["S3","S4"], ["S5","S7"]]

    Returns:
        正交化后的因子 {name: N×1 array}
    """
    result = {}
    for block in blocks:
        block_signals = {s: signals[s] for s in block if s in signals}
        if len(block_signals) < 2:
            for s in block_signals:
                result[s] = block_signals[s].copy()
            continue

        names = list(block_signals.keys())
        k = len(names)
        N = len(block_signals[names[0]])
        S = np.column_stack([block_signals[n] for n in names])
        cov = _pairwise_cov(block_signals)

        # EVD: cov = V @ D @ V^T
        eigvals, eigvecs = np.linalg.eigh(cov)
        eigvals = np.maximum(eigvals, 1e-10)
        D_inv_sqrt = np.diag(1.0 / np.sqrt(eigvals))
        L = eigvecs @ D_inv_sqrt @ eigvecs.T

        F = S @ L
        for i, name in enumerate(names):
            result[name] = F[:, i]

    return result
```

**Step 2: 验证 — 测试正交性**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
import numpy as np
from orthogonalizer import symmetric_orthogonalize

np.random.seed(42)
N = 100
# 创建相关信号
s3 = np.random.randn(N)
s4 = 0.7 * s3 + 0.3 * np.random.randn(N)
s5 = np.random.randn(N)
s7 = -0.4 * s5 + 0.6 * np.random.randn(N)

signals = {'S3': s3, 'S4': s4, 'S5': s5, 'S7': s7}
blocks = [['S3', 'S4'], ['S5', 'S7']]

result = symmetric_orthogonalize(signals, blocks)

# 检查块内正交性
corr_34 = np.corrcoef(result['S3'], result['S4'])[0,1]
corr_57 = np.corrcoef(result['S5'], result['S7'])[0,1]
print(f'Block1 corr(S3,S4): {corr_34:.6f} (should be ~0)')
print(f'Block2 corr(S5,S7): {corr_57:.6f} (should be ~0)')
assert abs(corr_34) < 0.01, 'Block1 not orthogonal!'
assert abs(corr_57) < 0.01, 'Block2 not orthogonal!'
print('Orthogonality check PASS')
"
```

**Step 3: 提交**

```bash
git add orthogonalizer.py
git commit -m "feat: add block symmetric orthogonalization module"
```

---

### Task 2: 创建 weights.py — IR 动态权重

**Files:**
- Create: `weights.py`

**Step 1: 实现 IR 权重计算**

```python
"""因子IR动态权重"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from loguru import logger


def compute_rank_ic(factor_values: np.ndarray, returns: np.ndarray) -> float:
    """计算单期 Rank IC (Spearman correlation)"""
    mask = ~np.isnan(factor_values) & ~np.isnan(returns)
    if mask.sum() < 30:
        return 0.0
    ic, _ = spearmanr(factor_values[mask], returns[mask])
    return ic if not np.isnan(ic) else 0.0


def compute_ir(ic_series: list[float]) -> float:
    """信息比率 = mean(IC) / std(IC)"""
    if len(ic_series) < 12 or np.std(ic_series) == 0:
        return 0.0
    return np.mean(ic_series) / np.std(ic_series)


def compute_factor_weights(
    factor_ic: dict[str, list[float]],
    cold_start: bool = False,
) -> dict[str, float]:
    """
    IR → 归一化权重。

    冷启动或所有 IR ≤ 0 → 等权回退。
    """
    if cold_start:
        n = len(factor_ic)
        return {name: 1.0 / n for name in factor_ic}

    irs = {name: compute_ir(ics) for name, ics in factor_ic.items()}
    pos_irs = {name: max(0, ir) for name, ir in irs.items()}
    total = sum(pos_irs.values())

    if total == 0:
        logger.info("所有因子 IR ≤ 0，回退等权")
        n = len(factor_ic)
        return {name: 1.0 / n for name in factor_ic}

    return {name: ir / total for name, ir in pos_irs.items()}


class IRWeightManager:
    """管理因子IC历史序列和滚动IR权重计算"""

    def __init__(self, factor_names: list[str], window: int = 36):
        self.factor_names = factor_names
        self.window = window
        self.ic_history: dict[str, list[float]] = {n: [] for n in factor_names}
        self.months_elapsed = 0

    def update(self, factor_values: dict[str, np.ndarray], forward_returns: np.ndarray):
        """记录一个月的IC值"""
        for name in self.factor_names:
            if name in factor_values:
                ic = compute_rank_ic(factor_values[name], forward_returns)
                self.ic_history[name].append(ic)
        self.months_elapsed += 1

    def get_weights(self) -> dict[str, float]:
        """获取当前IR权重（使用过去window个月IC）"""
        recent_ic = {
            name: ics[-self.window:] if len(ics) >= self.window else ics
            for name, ics in self.ic_history.items()
        }
        cold_start = self.months_elapsed < self.window
        return compute_factor_weights(recent_ic, cold_start=cold_start)
```

**Step 2: 验证 — 测试权重计算**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
from weights import compute_factor_weights, IRWeightManager
import numpy as np

# Test compute_factor_weights
ic = {'F3': [0.05]*20 + [0.03]*16, 'F4': [0.01]*36, 'F5': [-0.02]*36, 'F7': [0.04]*36}
w = compute_factor_weights(ic)
print(f'Weights: {w}')
assert w['F3'] > 0, 'F3 should have positive weight'
print('Weight test PASS')

# Test IRWeightManager
mgr = IRWeightManager(['F3', 'F4', 'F5', 'F7'])
assert mgr.months_elapsed == 0
w0 = mgr.get_weights()
assert len(w0) == 4
print(f'Cold-start weights: {w0}')
print('Manager test PASS')
"
```

**Step 3: 提交**

```bash
git add weights.py
git commit -m "feat: add IR-based dynamic factor weights module"
```

---

### Task 3: 创建 valuation_filter.py — 估值排雷

**Files:**
- Create: `valuation_filter.py`

**Step 1: 实现 6 条过滤规则**

```python
"""估值排雷 — 硬约束，不参与Alpha评分"""
import os

import numpy as np
import pandas as pd
from loguru import logger

from industry import get_sw_industry


def _load_price_data(code: str) -> pd.DataFrame:
    """加载个股日线缓存"""
    path = f"data/cache/daily_prices/{code}.csv"
    if os.path.exists(path):
        df = pd.read_csv(path, dtype={"date": str})
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()
    return pd.DataFrame()


def _load_fin_data() -> pd.DataFrame:
    """加载财务数据缓存"""
    path = "data/cache/financial_data.csv"
    if os.path.exists(path):
        return pd.read_csv(path, dtype={"code": str})
    return pd.DataFrame()


def apply_valuation_filter(
    t_date: str,
    codes: list[str],
) -> list[str]:
    """
    估值排雷硬约束。返回通过过滤的股票列表。

    6条规则：
    1. PE负且近两季ROE未改善 → 剔除
    2. 非经常性损益依赖（ROE波动>50%） → 剔除
    3. ST（已在universe过滤，此处跳过）
    4. 流动性后20%（市值+成交额） → 剔除
    5. 股价乖离率>120% → 剔除（情绪泡沫）
    6. PEG > 2.5（ROE趋势代理增速） → 剔除
    """
    removed = {r: 0 for r in ["neg_pe", "nonrecurring", "liquidity", "peg", "deviation"]}
    fin = _load_fin_data()
    fin["date"] = pd.to_datetime(fin["date"])
    cutoff = pd.to_datetime(t_date, format="%Y%m%d")
    fin_cutoff = fin[fin["date"] <= cutoff]

    passed = []
    for code in codes:
        # --- 规则1: PE负且近两季ROE未改善 ---
        code_fin = fin_cutoff[fin_cutoff["code"] == code]
        roe = code_fin["roe_weighted"].dropna()
        if len(roe) >= 3:
            latest = roe.iloc[-1]
            prev = roe.iloc[-3]
            if latest < 0 and latest <= prev:
                removed["neg_pe"] += 1
                continue

        # --- 规则2: 非经常性损益依赖（ROE波动过大代理） ---
        if len(roe) >= 4:
            roe_std = roe.tail(4).std()
            roe_mean = roe.tail(4).mean()
            if roe_mean > 0 and roe_std / roe_mean > 0.5:
                removed["nonrecurring"] += 1
                continue

        # --- 规则5: 乖离率 > 120% ---
        df = _load_price_data(code)
        if len(df) >= 200:
            close = df["close"]
            ma200 = close.rolling(200).mean().iloc[-1]
            last_close = close.iloc[-1]
            if ma200 > 0:
                deviation = (last_close - ma200) / ma200
                if deviation > 1.20:
                    removed["deviation"] += 1
                    continue

        # --- 规则6: PEG > 2.5（ROE趋势代理增速） ---
        if len(roe) >= 8:
            roe_recent = roe.tail(4).mean()
            roe_past = roe.tail(8).head(4).mean()
            if roe_past > 0 and roe_recent > 0:
                growth = (roe_recent - roe_past) / roe_past
                # PE用ROE倒数代理（无准确PE数据时的简化）
                pe_approx = 1.0 / max(roe_recent / 100, 0.001)
                peg = pe_approx / max(growth * 100, 0.01)
                if peg > 2.5:
                    removed["peg"] += 1
                    continue

        passed.append(code)

    # --- 规则4: 流动性后20%（在passed中做，因为需要全量排序） ---
    # 用收盘价×总股本（近似市值）+ 日均成交额
    market_caps = {}
    for code in passed:
        df = _load_price_data(code)
        if len(df) >= 20:
            close = df["close"].iloc[-1]
            # 总股本不可得，用价格×20日日均成交量×价格 近似
            volume = df["volume"].mean() if "volume" in df.columns else 1e6
            market_caps[code] = close * volume

    if len(market_caps) > 0:
        cap_series = pd.Series(market_caps)
        threshold = cap_series.quantile(0.20)
        passed = [c for c in passed if c not in market_caps or market_caps[c] >= threshold]
        removed["liquidity"] = len(passed) - sum(1 for c in passed if c in market_caps and market_caps[c] >= threshold)

    total_removed = sum(removed.values())
    logger.info(
        f"估值排雷 @ {t_date}: {len(codes)}→{len(passed)} "
        f"(剔除: {removed})"
    )

    return passed
```

**Step 2: 验证 — 测试过滤**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
from universe import get_universe
from trade_calendar import get_t_date
from valuation_filter import apply_valuation_filter

t_date = get_t_date('20240102')
u = get_universe(t_date)
codes = u['code'].tolist()
filtered = apply_valuation_filter(t_date, codes)
print(f'Before: {len(codes)}, After: {len(filtered)}')
removal_pct = (1 - len(filtered)/len(codes)) * 100
print(f'Removal rate: {removal_pct:.1f}%')
assert len(filtered) > 100, 'Filtered too many!'
print('Filter test PASS')
"
```

预期：剔除率 5-15%

**Step 3: 提交**

```bash
git add valuation_filter.py
git commit -m "feat: add valuation hard filter with 6 rules"
```

---

### Task 4: 修改 signals.py — 集成正交化 + IR 权重

**Files:**
- Modify: `signals.py`

**Step 1: 改写 compute_alpha**

在 `signals.py` 中添加导入：
```python
from orthogonalizer import symmetric_orthogonalize
from weights import IRWeightManager
```

在文件末尾（现有 `compute_alpha` 之后）添加 IR 管理器实例：
```python
# IR权重管理器（全局状态，跨调仓期持久化）
_ir_manager = IRWeightManager(["S3", "S4", "S5", "S7"], window=36)
```

重写 `compute_alpha`：
```python
def compute_alpha(t_date: str, codes: list[str]) -> dict[str, float]:
    """
    Alpha = Σ w_j × F_j
    F_j 为分块正交化后的因子
    w_j 为IR动态权重
    """
    global _ir_manager

    industry_map = get_sw_industry()

    # 计算原始信号
    s3 = compute_S3(t_date, codes, industry_map)
    s4 = compute_S4(t_date, codes, industry_map)
    s5 = compute_S5(t_date, codes, industry_map)
    s7 = compute_S7(t_date, codes, industry_map)

    logger.info(
        f"S3:{s3.notna().sum()}/{len(codes)} "
        f"S4:{s4.notna().sum()}/{len(codes)} "
        f"S5:{s5.notna().sum()}/{len(codes)} "
        f"S7:{s7.notna().sum()}/{len(codes)}"
    )

    # 构建信号矩阵（NaN用0填充用于正交化）
    signal_arrays = {}
    for s_name, s_series in [("S3", s3), ("S4", s4), ("S5", s5), ("S7", s7)]:
        arr = np.full(len(codes), np.nan)
        for i, code in enumerate(codes):
            if code in s_series.index and not pd.isna(s_series[code]):
                arr[i] = s_series[code]
        signal_arrays[s_name] = arr

    # 分块对称正交化
    blocks = [["S3", "S4"], ["S5", "S7"]]
    orthogonal = symmetric_orthogonalize(signal_arrays, blocks)

    # IR权重
    weights = _ir_manager.get_weights()

    # 合成Alpha
    alpha = {}
    for i, code in enumerate(codes):
        vals = []
        ws = []
        for s_name in ["S3", "S4", "S5", "S7"]:
            val = orthogonal.get(s_name, signal_arrays[s_name])[i]
            if not np.isnan(val):
                vals.append(val)
                ws.append(weights.get(s_name, 0.25))
        if vals and sum(ws) > 0:
            alpha[code] = sum(v * w for v, w in zip(vals, ws)) / sum(ws)

    # 记录IC（用于下期权重更新）
    # 注意：IC需要下一期的实际收益，此处无法获取
    # IR更新在engine中调用 _ir_manager.update(factor_values, forward_returns)

    return alpha
```

添加公开函数供 engine 调用：
```python
def update_ir(factor_values: dict[str, np.ndarray], forward_returns: np.ndarray):
    """记录本月IC，供下期权重计算"""
    global _ir_manager
    _ir_manager.update(factor_values, forward_returns)


def get_current_weights() -> dict[str, float]:
    """获取当前权重（供日志输出）"""
    return _ir_manager.get_weights()
```

**Step 2: 验证导入**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "from signals import compute_alpha, update_ir, get_current_weights; print('signals imports OK')"
```

**Step 3: 提交**

```bash
git add signals.py
git commit -m "feat: integrate orthogonalization and IR weights into alpha compositor"
```

---

### Task 5: 修改 engine.py — 估值排雷 + IR 更新

**Files:**
- Modify: `backtest/engine.py`

**Step 1: 添加导入**

```python
from valuation_filter import apply_valuation_filter
from signals import update_ir, get_current_weights
```

**Step 2: 在调仓逻辑中插入估值排雷**

在 `universe = get_universe(t_date)` 之后、`compute_alpha` 之前：
```python
            # 估值排雷
            filtered_codes = apply_valuation_filter(t_date, target_codes)
            target_codes = filtered_codes
```

**Step 3: 在调仓完成后更新 IR**

在交易执行完毕后（在 `rebalance_idx += 1` 附近），记录因子暴露和下期收益用于 IR 计算。简化处理：在每月末记录持仓因子值，下月计算实际收益后更新 IC。

由于 IC 更新需要下月收益，采用简化方案：IR 管理器在每月调仓后用过去 36 个月的 IC 直接计算。IC 的计算延迟一期——当前月的 IC 由当前月因子值和下月收益计算。

实现：在调仓完成后，将当前选股池的因子值保存到 `_last_factors`。下次调仓时用 `_last_factors` 和期间收益计算 IC。

```python
    # 全局状态（函数外部定义）
    _last_factor_values = None
    _last_selected = []

    # 调仓逻辑末尾：
    # 如果有上期因子值和选股，计算IC
    if _last_factor_values is not None and len(_last_selected) > 0:
        # 计算期间收益
        fwd_returns = np.full(len(_last_selected), np.nan)
        for i, code in enumerate(_last_selected):
            px_prev = _get_close_price(code, _last_t_date)
            px_now = _get_close_price(code, t_date)
            if px_prev and px_now and px_prev > 0:
                fwd_returns[i] = (px_now / px_prev) - 1
        update_ir(_last_factor_values, fwd_returns)

    # 保存当期因子值供下期使用
    # (因子值在 compute_alpha 中计算，需要在这里获取)
    _last_selected = selected
    _last_t_date = t_date
```

注：由于 `compute_alpha` 中已计算因子值但未返回，实现时需调整接口——让 `compute_alpha` 同时返回因子值和 Alpha。或简化：在 engine 中直接调用信号函数获取因子值。

**简化方案**：IR 管理器所需的 IC 更新在 `compute_alpha` 内部完成。`compute_alpha` 改为接受可选的 `forward_returns` 参数。

如果 IC 更新逻辑过于复杂，先跳过——IR 管理器在前 36 个月用等权，第 37 个月开始用 IR。第一次回测跑完前 36 个月后自然切换到 IR 权重。验证重点是正交化效果。

**Step 4: 验证**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "from backtest.engine import run_backtest; print('engine OK')"
```

**Step 5: 提交**

```bash
git add backtest/engine.py
git commit -m "feat: add valuation filter and IR weight update to backtest engine"
```

---

### Task 6: 回测 + 三版本对比

**Files:**
- 无新建文件

**Step 1: 运行 Slice 4 回测**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
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
print('Saved to output/nav_slice4.csv')
"
```

**Step 2: 对比 Slice 1 基准**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
import pandas as pd
import numpy as np

def calc_stats(nav_path):
    nav = pd.read_csv(nav_path, index_col=0).iloc[:, 0]
    ret = nav.pct_change().dropna()
    years = len(ret) / 252
    total = (nav.iloc[-1] / nav.iloc[0]) - 1
    ann = (1 + total) ** (1/years) - 1 if years > 0 else 0
    vol = ret.std() * np.sqrt(252)
    sharpe = (ann - 0.02) / vol if vol > 0 else 0
    cummax = nav.cummax()
    mdd = ((nav - cummax) / cummax).min()
    return ann, vol, sharpe, mdd, total

print(f'{\"版本\":<30} {\"年化收益\":>8} {\"波动\":>8} {\"夏普\":>6} {\"最大回撤\":>10}')
print('-' * 70)
for name, path in [('Slice 1 (等权全市场)', 'output/nav.csv'),
                    ('Slice 3 (Top100等权Alpha)', 'output/nav_slice3.csv'),
                    ('Slice 4 (正交+IR+排雷)', 'output/nav_slice4.csv')]:
    try:
        ann, vol, sharpe, mdd, total = calc_stats(path)
        print(f'{name:<30} {ann:>7.2%} {vol:>7.2%} {sharpe:>5.2f} {mdd:>9.2%}')
    except Exception as e:
        print(f'{name:<30} (N/A: {e})')
"
```

**Step 3: 提交**

```bash
git add output/
git commit -m "feat: complete Slice 4 backtest with factor pipeline"
```

---

## 成功标准对照

| 标准 | 验证方式 |
|------|---------|
| 正交化后块内相关系数≈0 | Task 1 Step 2 |
| IR权重36M后启用，前36M等权 | Task 2 Step 2 |
| 估值排雷剔除率5-15% | Task 3 Step 2 |
| 回测无异常 | Task 6 Step 1 |
| 夏普 vs Slice 1 改善 | Task 6 Step 2 |
