#!/usr/bin/env python3
"""从 snapshot JSON 生成待标注草稿。

用法:
  python tools/gen_label_todo.py --snapshot 20260601
  python tools/gen_label_todo.py --snapshot 20260601 --top 20

每周五跑一次，在 labels/attribution/_todo_{code}.yml 里预填系统字段，
人工只需改 human_gene / human_sub / human_persistence / why。
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TODO_DIR = ROOT / "labels" / "attribution"
SNAPSHOT_DIR = ROOT / "data" / "feedback" / "snapshot"

TEMPLATE = """# 待标注 — {name} ({code})
snapshot_date: {date}
code: "{code}"
name: {name}
industry_l3: {industry_l3}
l1_verdict: {l1_verdict}
composite: {composite}
system_gene: ???
system_sub: ???
system_persistence: ???
system_narrative: ???

human_gene: ???
human_sub: ???
human_persistence: ???
human_confidence: high
why: |
  TODO
"""


def main():
    parser = argparse.ArgumentParser(description="生成待标注草稿")
    parser.add_argument("--snapshot", required=True, help="快照日期 YYYYMMDD")
    parser.add_argument("--top", type=int, default=20, help="提取前 N 只")
    args = parser.parse_args()

    path = SNAPSHOT_DIR / f"{args.snapshot}.json"
    if not path.exists():
        print(f"Snapshot not found: {path}")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        snap = json.load(f)

    rows = snap.get("items", snap.get("rows", []))[:args.top]
    TODO_DIR.mkdir(parents=True, exist_ok=True)

    created = 0
    for row in rows:
        code = str(row.get("code", ""))
        name = str(row.get("name", code))
        out_path = TODO_DIR / f"_todo_{args.snapshot}_{code}_{name}.yml"
        if out_path.exists():
            continue  # 已有标注，跳过

        content = TEMPLATE.format(
            date=args.snapshot,
            code=code,
            name=name,
            industry_l3=row.get("industry_l3", row.get("industry", "")),
            l1_verdict=row.get("l1_verdict", "???"),
            composite=row.get("composite_score", row.get("composite", 0)),
        )
        out_path.write_text(content, encoding="utf-8")
        created += 1

    print(f"Generated {created} todo files in {TODO_DIR}")


if __name__ == "__main__":
    main()
