# Slice 5: 风险中性化 + 周期分层 IR 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 风险中性化消除 Beta 污染，周期分层 IR 让因子权重随牛/熊/结构市自适应

**Architecture:** 新增 risk_factors.py（4风险因子）+ neutralizer.py（横截面残差），扩展 weights.py（+CycleIRWeightManager），修改 signals.py（链路插入中性化+改用周期IR）。engine.py 不改

**Tech Stack:** Python 3.10, numpy, pandas, scipy, statsmodels

---

## 文件结构映射

| 文件 | 职责 | 依赖 |
|------|------|------|
| `risk_factors.py` | 计算 Beta/Size/Vol/Illiq 截面 | 日线缓存, CSI300指数 |
| `neutralizer.py` | OLS残差提取 | risk_factors |
| `weights.py` | +CycleIRWeightManager | regime/detector |
| `signals.py` | 链路重组：中性化→正交→周期IR | 以上全部 |
| `backtest/engine.py` | **不改** | — |

---

### Task 1: 创建 risk_factors.py

**Files:**
- Create: `risk_factors.py`

**Step 1: 实现 compute_risk_factors**

```python
"""风险因子计算：Beta, Size, Volatility, Illiquidity"""
import os
import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats


def _load_price_data(code: str) -> pd.DataFrame:
    path = f"data/cache/daily_prices/{code}.csv"
    if os.path.exists(path):
        df = pd.read_csv(path, dtype={"date": str})
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()
    return pd.DataFrame()


def _load_index_data() -> pd.Series:
    path = "data/cache/index_399300.csv"
    if os.path.exists(path):
        df = pd.read_csv(path, dtype={"date": str})
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")["close"]
    return pd.Series(dtype=float)


def compute_risk_factors(t_date: str, codes: list[str]) -> pd.DataFrame:
    """
    计算4个风险因子的截面向量。

    Returns:
        DataFrame index=code, columns=[beta, size, volatility, illiquidity]
    """
    cutoff = pd.to_datetime(t_date, format="%Y%m%d")
    index_close = _load_index_data()
    index_ret = index_close.pct_change().dropna()

    results = {}
    for code in codes:
        df = _load_price_data(code)
        if len(df) < 252:
            continue
        df = df[df.index <= cutoff]
        if len(df) < 252:
            continue
        close = df["close"]
        ret = close.pct_change().dropna().iloc[-252:]

        # Beta: 252日 OLS vs CSI300
        common = ret.index.intersection(index_ret.index)
        if len(common) < 100:
            continue
        ri = ret[common].values
        rm = index_ret[common].values
        slope, _, _, _, _ = stats.linregress(rm, ri)
        beta = slope

        # Size: log(close × avg_volume_20d)
        vol_col = "volume" if "volume" in df.columns else None
        avg_vol = df[vol_col].iloc[-20:].mean() if vol_col else 1e6
        size = np.log(max(close.iloc[-1] * avg_vol, 1))

        # Volatility: 60日 std
        vol60 = ret.iloc[-60:].std() if len(ret) >= 60 else ret.std()

        # Illiquidity: Amihud
        if vol_col:
            amihud_daily = np.abs(ret) / (df[vol_col] * close)
            illiq = np.log(np.mean(amihud_daily.iloc[-20:]) * 1e6 + 1e-10)
        else:
            illiq = 0.0

        results[code] = {
            "beta": beta, "size": size,
            "volatility": vol60, "illiquidity": illiq,
        }

    df = pd.DataFrame.from_dict(results, orient="index")
    df.index.name = "code"
    logger.info(f"风险因子 @ {t_date}: {len(df)}/{len(codes)} stocks")
    return df
```

**Step 2: 验证**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
from universe import get_universe
from trade_calendar import get_t_date
from risk_factors import compute_risk_factors
t_date = get_t_date('20240102')
codes = get_universe(t_date)['code'].tolist()[:100]
df = compute_risk_factors(t_date, codes)
print(f'Coverage: {len(df)}/{len(codes)}, cols={list(df.columns)}')
assert len(df) > 50
print('OK')
"
```

**Step 3: 提交**

```bash
git add risk_factors.py
git commit -m "feat: add risk factor calculation module (Beta, Size, Volatility, Illiquidity)"
```

---

### Task 2: 创建 neutralizer.py

**Files:**
- Create: `neutralizer.py`

**Step 1: 实现风险中性化**

```python
"""风险中性化 — 横截面OLS取残差"""
import numpy as np
import pandas as pd
from loguru import logger


def neutralize(
    signals: dict[str, np.ndarray],
    risk_factors: pd.DataFrame,
) -> dict[str, np.ndarray]:
    """
    对每个信号做横截面回归，剥除风险因子影响。

    Args:
        signals: {name: N×1 array}，NaN保留
        risk_factors: N×4 DataFrame with columns [beta, size, volatility, illiquidity]

    Returns:
        残差因子 {name: N×1 array}，NaN填入0
    """
    rf = risk_factors.values  # N×4
    result = {}
    for name, s_arr in signals.items():
        residual = np.full_like(s_arr, 0.0, dtype=float)
        mask = ~np.isnan(s_arr)
        if mask.sum() < 30:
            result[name] = residual
            continue

        y = s_arr[mask]
        X = rf[mask]
        # OLS: β = (X^T X)^(-1) X^T y
        try:
            XtX = X.T @ X
            XtX_inv = np.linalg.inv(XtX + np.eye(X.shape[1]) * 1e-6)
            beta = XtX_inv @ X.T @ y
            residual[mask] = y - X @ beta
        except np.linalg.LinAlgError:
            residual[mask] = y

        result[name] = residual

    logger.info(f"风险中性化完成: {len(signals)} signals")
    return result
```

**Step 2: 验证**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
import numpy as np
from neutralizer import neutralize

# Generate correlated data
np.random.seed(42)
N = 200
beta = np.random.randn(N)
size = np.random.randn(N)
rf = pd.DataFrame({'beta': beta, 'size': size, 'volatility': np.random.randn(N), 'illiquidity': np.random.randn(N)})
s3 = 0.5 * beta + 0.3 * size + 0.2 * np.random.randn(N)
signals = {'S3': s3}
result = neutralize(signals, rf)
# Check: residual should have low correlation with beta
corr = np.corrcoef(result['S3'], beta)[0,1]
print(f'Corr(residual, beta): {corr:.6f} (should be ~0)')
assert abs(corr) < 0.05
print('PASS')
"
```

**Step 3: 提交**

```bash
git add neutralizer.py
git commit -m "feat: add risk neutralization module (cross-sectional OLS)"
```

---

### Task 3: 扩展 weights.py — CycleIRWeightManager

**Files:**
- Modify: `weights.py`

**Step 1: 在现有 IRWeightManager 后追加**

```python
class CycleIRWeightManager:
    """周期分层IR权重管理器。按BULL/STRUCT/BEAR分层存储IC历史。"""

    def __init__(self, factor_names: list[str], window: int = 36):
        self.factor_names = factor_names
        self.window = window
        self.months_elapsed = 0
        self.ic_history = {"BULL": {}, "STRUCT": {}, "BEAR": {}}
        for regime in self.ic_history:
            self.ic_history[regime] = {n: [] for n in factor_names}
        self.regime_history: list[str] = []

    def update(self, factor_values: dict[str, np.ndarray], forward_returns: np.ndarray, regime: str):
        """记录一个月IC，按Regime分层"""
        from weights import compute_rank_ic
        for name in self.factor_names:
            if name in factor_values:
                ic = compute_rank_ic(factor_values[name], forward_returns)
                self.ic_history[regume][name].append(ic)
        self.regime_history.append(regime)
        self.months_elapsed += 1

    def get_weights(self, regime: str) -> dict[str, float]:
        """当前Regime对应的IR权重，样本不足回退全周期"""
        from weights import compute_factor_weights

        if self.months_elapsed < self.window:
            n = len(self.factor_names)
            return {name: 1.0 / n for name in self.factor_names}

        # 取当前Regime的IC子集
        regime_ic = self.ic_history.get(regime, {})
        if all(len(ics) >= 12 for ics in regime_ic.values()):
            return compute_factor_weights(regime_ic, cold_start=False)

        # 回退全周期
        all_ic = {}
        for name in self.factor_names:
            combined = []
            for r_ics in self.ic_history.values():
                combined.extend(r_ics.get(name, []))
            all_ic[name] = combined[-self.window:]
        return compute_factor_weights(all_ic, cold_start=False)
```

**Step 2: 验证**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
from weights import CycleIRWeightManager
mgr = CycleIRWeightManager(['F3','F4','F5','F7'])
w = mgr.get_weights('BULL')
assert len(w) == 4
for v in w.values():
    assert abs(v - 0.25) < 0.01
print(f'Cold start: {w}')
print('PASS')
"
```

**Step 3: 提交**

```bash
git add weights.py
git commit -m "feat: add cycle-stratified IR weight manager (BULL/STRUCT/BEAR)"
```

---

### Task 4: 修改 signals.py — 链路重组

**Files:**
- Modify: `signals.py`

**Step 1: 添加导入 + 替换 IR 管理器**

将：
```python
from weights import IRWeightManager
_ir_manager = IRWeightManager(["S3", "S4", "S5", "S7"], window=36)
```

改为：
```python
from weights import CycleIRWeightManager
from risk_factors import compute_risk_factors
from neutralizer import neutralize
from regime.detector import detect_regime

_ir_manager = CycleIRWeightManager(["S3", "S4", "S5", "S7"], window=36)
```

**Step 2: 在 compute_alpha 中插入中性化 + 周期IR**

在信号数组构建完成后、正交化之前插入：

```python
    # 风险中性化
    try:
        risk_df = compute_risk_factors(t_date, codes)
        neutralized = neutralize(signal_arrays, risk_df)
    except Exception:
        logger.warning(f"风险中性化失败，使用原始信号")
        neutralized = signal_arrays

    blocks = [["S3", "S4"], ["S5", "S7"]]
    orthogonal = symmetric_orthogonalize(neutralized, blocks)
```

IR 权重部分改为：

```python
    regime_result = detect_regime(t_date)
    weights = _ir_manager.get_weights(regime_result.regime)
    logger.info(f"Regime={regime_result.regime} IR weights: {weights}")
```

**Step 3: 验证**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "from signals import compute_alpha; print('OK')"
```

**Step 4: 提交**

```bash
git add signals.py
git commit -m "feat: integrate risk neutralization and cycle-stratified IR into alpha pipeline"
```

---

### Task 5: 回测 + 对比

**Step 1: 运行回测**

```bash
cd /Users/nayiahlu/Documents/自研项目/python项目/周期驱动因子系统
.venv/bin/python -c "
import os
from backtest.engine import run_backtest
result = run_backtest('20150101', '20241231')
stats = result.stats
print()
print('=== Slice 5 (风险中性化+周期IR) ===')
for k, v in stats.items():
    print(f'  {k}: {v}')
os.makedirs('output', exist_ok=True)
result.nav_series.to_csv('output/nav_slice5.csv', header=['nav'])
print('Saved to output/nav_slice5.csv')
"
```

**Step 2: 对比**

```bash
.venv/bin/python -c "
import pandas as pd, numpy as np
def s(p):
    nav = pd.read_csv(p, index_col=0).iloc[:,0]
    ret = nav.pct_change().dropna()
    y = len(ret)/252
    t = (nav.iloc[-1]/nav.iloc[0])-1
    a = (1+t)**(1/y)-1
    v = ret.std()*np.sqrt(252)
    sh = (a-0.02)/v
    dd = ((nav-nav.cummax())/nav.cummax()).min()
    return a,v,sh,dd
for name, path in [('Slice 1 等权','output/nav.csv'),('Slice 4 正交+IR','output/nav_slice4.csv'),('Slice 5 中性+周期','output/nav_slice5.csv')]:
    a,v,sh,dd = s(path)
    print(f'{name:<25} {a:>7.2%} {v:>7.2%} {sh:>5.2f} {dd:>9.2%}')
"
```

**Step 3: 提交**

```bash
git add -f output/nav_slice5.csv run_slice5.py
git commit -m "feat: complete Slice 5 backtest with risk neutralization + cycle-stratified IR"
```

---

## 成功标准对照

| 标准 | 验证 |
|------|------|
| 风险因子覆盖率 > 80% | Task 1 Step 2 |
| 中性化后残差⊥风险因子 | Task 2 Step 2 |
| 周期IR分层启用 | Task 3 Step 2 |
| 链路导入正常 | Task 4 Step 3 |
| 夏普 vs Slice 4 改善 | Task 5 Step 2 |
