# 运行期冻结确认（2026-09-03）

## 冻结基线
```
v35-runtime
+ L-relative Design Note v0.1 (含触发条件/Reference Class 护栏)
+ Calibration Library v0.1 (四类样本)
```

## 边界（不做）
- ❌ L-relative v1 开发
- ❌ 修改评分模型 / L1 逻辑 / Growth OS 主模型
- ❌ 增加更多指标

## 进入条件（Calibration ≥10 样本后）
- v4 设计输入 = 哪些信号经过验证真的值得相信

## 恒瑞 CAL-001 最终标签（不再修改）
- status: PENDING_VALIDATION
- type: calibration_sample (非 system_failure)
- current_learning: low_base_bias / leading_result_divergence / reference_class_selection
- next_check: Q3 + 创新药收入 + BD + Peer relative

## 运行期唯一任务
> 让系统犯错，让 Calibration Library 长出来（假机会/漏机会/正确机会/归因错误 四类）
