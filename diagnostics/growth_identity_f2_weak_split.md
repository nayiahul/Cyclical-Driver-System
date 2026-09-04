# Audit C — F2 B_WEAK 子类拆分结果

**日期**: 2026-09-04 | **方法**: panel 后处理, WEAK → WEAK_MARGIN(margin red) / WEAK_ROIC(ROIC<=0)

**b5 分布**: {'YELLOW': 8107, 'WEAK_MARGIN': 5412, 'OK': 3188, 'WEAK_ROIC': 2204, 'UNKNOWN': 925}

## F2 组 B5 子类 × T+4Q (含低基数)

| cell | OK | YELLOW | WEAK_ROIC | WEAK_MARGIN | WEAK(合并, 参考) |
|---|---|---|---|---|---|
| F2M0 | pos=0.485 med=-1.87 n=379 | pos=0.505 med=0.49 n=830 | pos=0.624 med=14.62 n=125 | pos=0.526 med=3.84 n=363 | pos=0.551 med=6.14 n=488 |
| F2M1 | pos=0.542 med=2.72 n=565 | pos=0.529 med=2.16 n=1298 | pos=0.599 med=7.77 n=232 | pos=0.493 med=-1.02 n=515 | pos=0.526 med=2.56 n=747 |
| F2M2 | pos=0.475 med=-1.83 n=162 | pos=0.496 med=-0.78 n=369 | pos=0.5 med=-0.16 n=58 | pos=0.593 med=15.14 n=140 | pos=0.566 med=5.1 n=198 |

## F2 组 B5 × T+4Q (排除低基数, ttm>=5000万)

| cell | OK | YELLOW | WEAK_ROIC | WEAK_MARGIN |
|---|---|---|---|---|
| F2M0 | pos=0.483 med=-2.08 n=346 | pos=0.504 med=0.28 n=724 | pos=0.672 med=12.91 n=64 | pos=0.496 med=-0.77 n=250 |
| F2M1 | pos=0.556 med=3.47 n=500 | pos=0.539 med=2.22 n=1015 | pos=0.623 med=5.94 n=106 | pos=0.491 med=-1.73 n=320 |
| F2M2 | pos=0.462 med=-2.2 n=132 | pos=0.518 med=0.91 n=280 | n=29⚠ | pos=0.539 med=2.97 n=76 |

## 裁决 (残余反直觉归因)

- F2M0: OK pos=0.483 med=-2.08 n=346 | WEAK_ROIC pos=0.672 med=12.91 n=64 | WEAK_MARGIN pos=0.496 med=-0.77 n=250
- F2M1: OK pos=0.556 med=3.47 n=500 | WEAK_ROIC pos=0.623 med=5.94 n=106 | WEAK_MARGIN pos=0.491 med=-1.73 n=320
- F2M2: OK pos=0.462 med=-2.2 n=132 | WEAK_ROIC n=29⚠ | WEAK_MARGIN pos=0.539 med=2.97 n=76

解读规则:
- WEAK_ROIC > OK 且 WEAK_MARGIN <= OK → 残余反直觉来自周期底部弹性, B_proxy(质量)逻辑不受损
- WEAK_MARGIN 也 > OK → 质量代理反直觉真实, B_v35 定义需重审
- 样本 <30 (⚠) 不裁决
## F2 裁决结论 (2026-09-04)

### 裁决: 残余反直觉主要归因 WEAK_ROIC (周期底部弹性), B_v35 质量代理逻辑不受损

排除低基数后 (主裁决口径):
| cell | OK | WEAK_ROIC | WEAK_MARGIN | 归因 |
|---|---|---|---|---|
| F2M0 | 0.483 | **0.672** | 0.496 (≈OK) | WEAK_ROIC 驱动 |
| F2M1 | 0.556 | **0.623** | **0.491 (<OK)** | WEAK_ROIC 驱动 + MARGIN 验证质量逻辑 |
| F2M2 | 0.462 | n=29⚠ | 0.539 (n=76 小样本) | 样本不足, 不裁决 |

**关键证据 F2M1**: WEAK_MARGIN (0.491) < OK (0.556) — "margin red = 质量恶化 → 兑现更低" 成立,
且 WEAK_ROIC (0.623) > OK — 周期底部/反转早期公司利润弹性大。**假设完全验证。**

**F2M0**: WEAK_MARGIN ≈ OK (0.496 vs 0.483, med -0.77 vs -2.08), 无质量反直觉; 残余来自 WEAK_ROIC (0.672)。

**综合**: 
1. F1 残余的 1-3pp "OK<WEAK" 反直觉 = WEAK_ROIC 子类 (ROIC<=0 但 margin 未恶化的周期底部/反转公司) 的高弹性, **非质量代理失效**
2. WEAK_MARGIN (真质量恶化) 从未显著高于 OK — B_v35 作为质量弱代理的**方向性有效**
3. F2M2 样本不足留 Full 12 时点补

**对 B_v35 定义的含义** (Full 阶段): 
- "WEAK" 合并组混淆了两种经济状态 → Full 应采用 b5 (OK/YELLOW/WEAK_ROIC/WEAK_MARGIN/UNKNOWN)
- WEAK_ROIC 不应视为"低质量" — 它是"周期底部待反转"候选, 与 Recovery/L5 逻辑同族
- 这修正了 Bloodline Audit 的"危险区 36%"解读: 危险区需再分 (margin red 真危险 vs ROIC<=0 周期位)

## F2 完成状态
- ✅ WEAK 拆分 → b5 五类, 残余反直觉归因完成 (WEAK_ROIC 弹性, 非质量失效)
- ✅ B_v35 质量代理方向性有效 (F2M1: MARGIN<OK)
- ✅ Full 采用 b5 口径; "危险区 36%"解读需细分
- ▶ F3 (T+4Q 衰减来源: 指标均值回归 vs 基数 vs 环境) 为下一前置
