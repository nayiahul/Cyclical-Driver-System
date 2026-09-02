# E Calibration v1 — Attention 维度验证结果

**日期**: 2026-09-02（Step 12-A）
**问题**: 低 RPS = "市场忽略" 是错误映射；需区分"真忽略"与"高关注回调"

## 结果（1800 低 RPS 样本, 2022-2025）

### 分类分布
TRUE_IGNORED 1242 (69%) / HIGH_ATTN_DROP 27 / HIGH_ATTN_STRONG 14 / OTHER 517

### fwd6 对照
| 分类 | 全样本 fwd6 | L1候选内(discovery≥0.5) |
|---|---|---|
| TRUE_IGNORED（真忽略） | +8.4% | **+8.7%** |
| HIGH_ATTN_DROP（高关注回调） | -1.1% | **+0.4%** |
| HIGH_ATTN_STRONG（高位强势） | -5.2% | — |
| OTHER | +4.1% | +4.0% |

## 结论

1. **误判成本 = 8.3pp**: 高关注回调被标 E0 混入 A 级池后, 其 L1 候选 fwd6 仅 +0.4% vs 真忽略 +8.7%
2. **高关注回调即使基本面强也不涨** (+0.4%) — 预期差已被前期大涨消耗
3. 原 E0 需分离: Attention 维度是必要条件

## E v2 规则草案（Shadow 待测）

```
E0 TRUE_IGNORED: ret_252d<50% 且 amt_ratio<1.0 （从未被关注）
E5 HIGH_ATTN_DROP: ret_252d>100% 且 距高点<-20%（高关注回调, 非预期差）
E4 HIGH_ATTN_STRONG: ret_252d>100% 且 距高点>-20%（高位）
```

## 数据
- baseline/e_calibration_v1.csv（1800 行）
- 复跑: tools/e_calibration_v1.py
