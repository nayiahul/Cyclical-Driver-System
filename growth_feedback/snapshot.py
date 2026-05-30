"""每日预测快照 — 结构化保存Top20预测数据,供后续市场结果对账。

输出: data/feedback/snapshot/YYYYMMDD.json
每天一个文件,包含当日Top20的完整预测状态。
"""
from __future__ import annotations
import json, os
from datetime import datetime
import pandas as pd


def save_snapshot(top20_df: pd.DataFrame, t_date: str, output_dir: str = "data/feedback/snapshot"):
    """保存当日Top20预测快照为JSON。"""
    os.makedirs(output_dir, exist_ok=True)
    records = []
    for _, r in top20_df.iterrows():
        records.append({
            "code": str(r.get("code", "")),
            "name": str(r.get("name", "")),
            "industry": str(r.get("industry_l3", "")),
            "lifecycle": str(r.get("lifecycle", "")),
            "composite": float(r.get("composite_score", 0)),
            "persistence": float(r.get("persistence_score", 0)) if not pd.isna(r.get("persistence_score", 0)) else 0,
            "source": str(r.get("stock_regime", "")),
            "decision": str(r.get("decision", "")),
            "risk_tags": str(r.get("risk_tags", "")),
            "l2": float(r.get("score_l2", 0)),
            "l3": float(r.get("score_l3", 0)),
        })
    path = os.path.join(output_dir, f"{t_date}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": t_date, "generated": datetime.now().isoformat(),
                    "count": len(records), "items": records}, f, ensure_ascii=False, indent=2)
    return path
