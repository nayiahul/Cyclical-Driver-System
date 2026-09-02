"""Step 7-C: Investment Decision CLI — 投资判断留痕系统。

不是"人工打分", 是"判断留痕":
  记录 当时基于什么证据 → 做了什么决策 → 承担什么风险 → 什么情况证明错

Decision 枚举: IGNORE / WATCH / DEEP_RESEARCH / HOLD / DROP
Conviction: LOW / MEDIUM / HIGH
核心字段: thesis(why_now) + key_risk + counter_thesis(为什么可能错) + expected_path

输出: data/ledger/decisions.jsonl (与 outcomes.jsonl 通过 stock+research_date 关联)

用法:
  python tools/decision_cli.py --book output/research_book_20260901.csv
  python tools/decision_cli.py --book ... --resume   # 跳过已决策的
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

DECISIONS = ["WATCH", "DEEP_RESEARCH", "IGNORE", "HOLD", "DROP"]
CONVICTIONS = ["LOW", "MEDIUM", "HIGH"]
LEDGER = "data/ledger/decisions.jsonl"

SCHEMA_DOC = "docs/OUTCOME_LEDGER_SCHEMA.md 对象2: InvestmentDecision (+ counter_thesis 扩展)"


def prompt_choice(label: str, options: list[str]) -> str:
    while True:
        print(f"\n{label}:")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        try:
            n = int(input("选择 > ").strip())
            if 1 <= n <= len(options):
                return options[n - 1]
        except (ValueError, EOFError):
            pass
        print("无效输入，重试")


def prompt_text(label: str, optional: bool = False) -> str:
    while True:
        val = input(f"{label} > ").strip()
        if val or optional:
            return val
        print("不能为空")


def main():
    ap = argparse.ArgumentParser(description="投资判断留痕 CLI")
    ap.add_argument("--book", required=True, help="Daily Research Book CSV")
    ap.add_argument("--resume", action="store_true", help="跳过已决策股票")
    args = ap.parse_args()

    df = pd.read_csv(args.book)
    df["code"] = df["code"].astype(str).str.zfill(6)
    research_date = os.path.basename(args.book).replace("research_book_", "")[:8]

    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    done = set()
    if args.resume and os.path.exists(LEDGER):
        for line in open(LEDGER):
            try:
                done.add(json.loads(line)["stock_code"])
            except Exception:
                pass

    n = 0
    for _, row in df.iterrows():
        code = row["code"]
        if code in done:
            continue

        print("\n" + "=" * 60)
        print(f"{code} [{row['research_stage']}] radar={row['radar']} priority={row['research_priority']}")
        print("=" * 60)
        if pd.notna(row["drivers"]):
            print(f"Why Now:\n  {row['drivers'][:150]}")
        if pd.notna(row["risks"]) and str(row["risks"]).strip():
            print(f"Risk:\n  {row['risks'][:120]}")

        decision = prompt_choice("Decision", DECISIONS)
        if decision == "IGNORE":
            conviction = "LOW"
        else:
            conviction = prompt_choice("Conviction", CONVICTIONS)

        thesis = prompt_text("Thesis (你的判断依据, 简短)", optional=True)
        counter = prompt_text("Counter Thesis (什么情况下你的判断是错的?)", optional=True)
        check = prompt_text("Check Points (要验证什么, 逗号分隔)", optional=True)

        rec = {
            "stock_code": code,
            "research_date": research_date,
            "radar": row["radar"],
            "state_at_memo": row["lifecycle_state"],
            "decision": decision,
            "conviction": conviction,
            "thesis": thesis,
            "counter_thesis": counter,
            "check_points": [c.strip() for c in check.split(",") if c.strip()],
            "key_risk": str(row["risks"]) if pd.notna(row["risks"]) else "",
            "expected_path": {
                "bull": "L5→L2" if row["radar"] == "recovery_radar" else "L1→L2/L3",
                "base": "保持观察",
                "bear": "→L0（判断证伪）",
            },
            "created_by": "human",
            "created_at": datetime.now().isoformat(),
            "schema": SCHEMA_DOC,
        }
        with open(LEDGER, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        n += 1
        print(f"✓ 已记录: {code} [{decision}/{conviction}]")

    print(f"\n完成: 新增 {n} 条判断 → {LEDGER}")
    if os.path.exists(LEDGER):
        total = sum(1 for _ in open(LEDGER))
        print(f"累计判断: {total} 条")


if __name__ == "__main__":
    main()
