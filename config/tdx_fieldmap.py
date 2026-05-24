"""通达信 gpcw 财务数据字段映射

从 config/tdx_fields.csv 加载，该文件由通达信官方 Excel 字段清单生成。
映射变化时只需更新 CSV，无需改代码。
"""
import os

import pandas as pd

_CSV_PATH = os.path.join(os.path.dirname(__file__), "tdx_fields.csv")

# 从 CSV 加载字段映射
_fields_df = pd.read_csv(_CSV_PATH, comment="#")

# {变量名: {col, name, category, unit, valid_range}}
TDX_FIELDS = {}
for _, row in _fields_df.iterrows():
    spec = {
        "col": int(row["col"]),
        "desc": row["name"],
        "unit": row.get("unit", "元"),
    }
    vr = row.get("valid_range")
    if pd.notna(vr) and str(vr).strip():
        lo, hi = vr.split(",")
        spec["valid_range"] = (float(lo), float(hi))
    TDX_FIELDS[row["variable"]] = spec

# 用于校验的关键列
CRITICAL_COLS = [
    ("col191", "扣非净利润同比"),
    ("col233", "扣非净利润单季度"),
    ("col434", "合同负债"),
]

# Winsorize 阈值（仅增长率字段，绝对金额不再做跨截面截断）
WINSORIZE_MIN = 1
WINSORIZE_MAX = 99

# 低基数过滤: 去年同季度扣非净利润 < 此值 → 排除同比信号
MIN_BASE_PROFIT = 10_000_000  # 1000万元
