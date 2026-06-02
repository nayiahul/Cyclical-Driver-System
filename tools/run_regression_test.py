#!/usr/bin/env python3
"""归因标注集回归测试。

用法:
  python tools/run_regression_test.py --snapshot 20260601
  python tools/run_regression_test.py --eval annotations/sprint20_eval.yaml --snapshot 20260601

每次改 classifier.py / industry_template.py 后跑一遍，确保没把以前对的改错。
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _simple_yaml_load(path: pathlib.Path) -> dict:
    """Minimal YAML loader for our eval format (no pyyaml dependency)."""
    result: dict = {}
    current_key = ""
    current_list: list = []
    in_entries = False
    entry: dict = {}
    in_reason = False
    reason_lines: list = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.rstrip()
            # skip comments and empty
            if stripped.startswith("#") or not stripped:
                continue

            if stripped.startswith("entries:"):
                in_entries = True
                continue

            if in_entries and stripped.startswith("  - "):
                if entry:
                    if reason_lines:
                        entry["reason"] = " ".join(reason_lines)
                        reason_lines = []
                    current_list.append(entry)
                    entry = {}
                    in_reason = False
                # parse key: value on same line
                rest = stripped[4:]  # remove "  - "
                if ":" in rest:
                    k, v = rest.split(":", 1)
                    entry[k.strip()] = v.strip()
                continue

            if in_entries and stripped.startswith("    ") and ":" in stripped:
                if in_reason:
                    in_reason = False
                    entry["reason"] = " ".join(reason_lines)
                    reason_lines = []
                k, v = stripped.strip().split(":", 1)
                entry[k.strip()] = v.strip().strip('"').strip("'")
                if k.strip() == "reason":
                    in_reason = True
                continue

            if in_entries and in_reason and stripped.startswith("      "):
                reason_lines.append(stripped.strip())
                continue

    if entry:
        if reason_lines:
            entry["reason"] = " ".join(reason_lines)
        current_list.append(entry)

    return {"entries": current_list}


def load_eval(path: pathlib.Path) -> list[dict]:
    return _simple_yaml_load(path).get("entries", [])



def check_one(entry: dict) -> list[str]:
    """对单条标注跑 classify()，返回差异列表。"""
    errors = []
    human_gene = str(entry.get("gene_human", "")).strip('"').strip("'")
    human_sub = str(entry.get("sub_gene_human", "")).strip('"').strip("'")
    confidence = float(str(entry.get("confidence_human", 0)))

    if confidence < 0.7:  # 仅检查 high confidence 标注
        return errors

    ticker = str(entry["ticker"]).strip('"').strip("'")
    date = str(entry["date"]).replace("-", "")
    name = entry.get("name", ticker)

    from growth_os.data import load_industry_map
    from growth_os.funnel import run_funnel
    from growth_os.scorecard import GrowthScorecard, compute_composite
    from growth_source.classifier import classify, get_roic_volatility
    from growth_os.config import LifecycleStage

    ind_map = load_industry_map()
    industry_l3 = ind_map.get(ticker, "")

    funnel = run_funnel(ticker, date, industry_l3, LifecycleStage.ACCELERATION)
    card = GrowthScorecard(
        code=ticker, name=name,
        industry_l3=industry_l3, industry_l1="",
        lifecycle=LifecycleStage.ACCELERATION, lifecycle_reason="",
        pass_l1=funnel.get("pass_l1", True),
        l1_verdict=funnel.get("l1_verdict", "pass"),
        l1_red_flags=funnel.get("l1_red_flags", []),
        score_l2=funnel.get("score_l2", 0),
        score_l3=funnel.get("score_l3", 0),
        score_l4=funnel.get("score_l4", 0),
        score_l5=funnel.get("score_l5", 0),
    )
    card = compute_composite(card, funnel)
    stock = card.to_dict()
    stock["code"] = ticker
    stock["name"] = name
    stock["industry_l3"] = industry_l3
    stock["industry_l1"] = ""

    gm_label = str(stock.get("gross_margin_trend", ""))
    roic_vol = get_roic_volatility(ticker, date)
    attr = classify(stock, gm_label, roic_vol)

    if human_gene and attr.source != human_gene:
        errors.append(f"GENE: sys={attr.source} human={human_gene}")
    if human_sub and attr.sub_gene != human_sub:
        errors.append(f"SUB:  sys={attr.sub_gene or '-'} human={human_sub}")

    return errors


def main():
    parser = argparse.ArgumentParser(description="归因标注集回归测试")
    parser.add_argument("--eval", default="annotations/sprint20_eval.yaml",
                        help="标注文件路径")
    parser.add_argument("--snapshot", default="20260601", help="快照日期(备用)")
    args = parser.parse_args()

    eval_path = ROOT / args.eval
    if not eval_path.exists():
        print(f"Eval file not found: {eval_path}")
        sys.exit(1)

    entries = load_eval(eval_path)

    total, failed, skipped = 0, 0, 0
    for entry in entries:
        if float(entry.get("confidence_human", 0)) < 0.7:
            skipped += 1
            continue
        total += 1
        errors = check_one(entry)
        if errors:
            failed += 1
            print(f"\n❌ {entry['ticker']} {entry['name']}")
            for e in errors:
                print(f"   {e}")
        else:
            print(f"✅ {entry['ticker']} {entry['name']}")

    print(f"\n=== Regression Test ===")
    print(f"Checked: {total}  Passed: {total-failed}  Failed: {failed}  Skipped(low conf): {skipped}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
