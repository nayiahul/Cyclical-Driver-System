"""Gate 0 冻结工具 — 生成回测 Baseline Artifact（manifest + 环境 + 数据 hash）。

用途:
    任何回测必须声明 strategy_version + data_snapshot 才能比较。
    本工具生成:
      manifest.json      # baseline_id, snapshot_id, commit, tag, env, params, 输入文件 hash
      environment.txt    # pip freeze 全量
      data_snapshot.txt  # 输入文件清单 (sha256/rows/min/max)

用法:
    python tools/gate0_freeze.py --baseline-id pre_pit_20260901_001 \
                                 --snapshot-id snapshot_20260901_001 \
                                 --out-dir baseline/pre_pit \
                                 --note "PRE-PIT baseline, INVALID_FOR_VALIDATION"

设计原则:
    - 只读数据，不修改业务代码
    - 目录 hash = sha256(全部文件内容 hash 排序拼接)，文件内容变化即 hash 变化
    - 价格目录 (STOCKS_DIR) 做全文件内容 hash + 首/末行日期采样
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_CACHE = os.path.join(ROOT, "data", "cache")

# 输入文件清单（相对 ROOT），来自 docs/DATA_INVENTORY.md
INPUT_FILES = [
    "data/cache/tdx_financials.csv",
    "data/cache/financial_data.csv",
    "data/cache/disclosure_calendar.csv",
    "data/cache/quality_snapshot.csv",
    "data/cache/stock_list.csv",
    "data/cache/trade_calendar.csv",
    "data/cache/sw_stock_industry.csv",
    "data/cache/sw_hierarchy.csv",
    "data/cache/sw_industry_map.csv",
    "data/cache/sw_industry_map_full.csv",
    "data/cache/bond_10y.csv",
    "data/cache/etf_511010_bond.csv",
    "data/cache/index_000922_dividend.csv",
    "data/cache/index_399006.csv",
    "data/cache/index_399300.csv",
    "data/cache/margin_data.csv",
    "data/cache/market_pe.csv",
    "data/cache/pdf_financials.csv",
    "config/params.py",
    "config/tdx_fields.csv",
]

DATE_COLS = ("date", "trade_date", "report_date", "report_date_str", "disclosure_date")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def csv_bounds(path: str) -> tuple[str | None, str | None]:
    """返回 (min_date, max_date)，用第一个存在的日期列；失败返回 (None, None)。"""
    try:
        import pandas as pd

        head = pd.read_csv(path, nrows=50)
        date_col = next((c for c in DATE_COLS if c in head.columns), None)
        if date_col is None:
            return None, None
        full = pd.read_csv(path, usecols=[date_col], dtype=str)
        vals = full[date_col].dropna().astype(str).str[:10]
        if vals.empty:
            return None, None
        return vals.min(), vals.max()
    except Exception:
        return None, None


def file_entry(rel: str) -> dict:
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return {"path": rel, "status": "MISSING"}
    mn, mx = csv_bounds(path)
    return {
        "path": rel,
        "sha256": sha256_file(path),
        "size_bytes": os.path.getsize(path),
        "rows": sum(1 for _ in open(path, "rb")) - 1 if path.endswith(".csv") else None,
        "min_date": mn,
        "max_date": mx,
    }


def price_dir_entry(stocks_dir: str) -> dict:
    """价格目录：全文件内容 hash 聚合 + 首/末行日期采样。"""
    files = sorted(f for f in os.listdir(stocks_dir) if f.endswith(".csv"))
    if not files:
        return {"path": stocks_dir, "status": "EMPTY"}
    digests = []
    total_bytes = 0
    first_dates, last_dates = [], []
    for name in files:
        p = os.path.join(stocks_dir, name)
        total_bytes += os.path.getsize(p)
        digests.append(sha256_file(p))
        with open(p, "r", errors="ignore") as f:
            lines = f.readlines()
        if len(lines) >= 2:
            first_dates.append(lines[1].split(",")[0])
            last_dates.append(lines[-1].split(",")[0])
    agg = hashlib.sha256("".join(digests).encode()).hexdigest()
    return {
        "path": stocks_dir,
        "kind": "price_dir",
        "n_files": len(files),
        "total_bytes": total_bytes,
        "aggregate_sha256": agg,
        "sample_min_date": min(first_dates) if first_dates else None,
        "sample_max_date": max(last_dates) if last_dates else None,
        "note": "min/max 为全文件首/末行日期采样",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Gate 0 冻结工具")
    ap.add_argument("--baseline-id", required=True)
    ap.add_argument("--snapshot-id", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--stocks-dir", default=os.path.join(os.path.expanduser("~"), "Desktop", "stocks"))
    args = ap.parse_args()

    out_dir = os.path.join(ROOT, args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # 1) 环境冻结
    env = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {},
    }
    try:
        import pandas, numpy, loguru  # noqa
        env["packages"] = {
            "pandas": pandas.__version__,
            "numpy": numpy.__version__,
            "loguru": loguru.__version__,
        }
    except Exception as e:
        env["packages"]["error"] = str(e)
    try:
        freeze = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True, text=True, timeout=60,
        ).stdout
        with open(os.path.join(out_dir, "environment.txt"), "w") as f:
            f.write(freeze)
        env["pip_freeze"] = "environment.txt"
    except Exception as e:
        env["pip_freeze"] = f"ERROR: {e}"

    # 2) 输入文件 hash
    files = [file_entry(rel) for rel in INPUT_FILES]
    prices = price_dir_entry(args.stocks_dir)

    # 3) git 信息
    git = {"commit": None, "tag": None, "dirty": None}
    try:
        git["commit"] = subprocess.run(
            ["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        git["tag"] = subprocess.run(
            ["git", "-C", ROOT, "describe", "--tags", "--exact-match", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip() or None
        git["dirty"] = bool(subprocess.run(
            ["git", "-C", ROOT, "status", "--porcelain"],
            capture_output=True, text=True,
        ).stdout.strip())
    except Exception as e:
        git["error"] = str(e)

    manifest = {
        "baseline_id": args.baseline_id,
        "data_snapshot_id": args.snapshot_id,
        "generated_at": datetime.now().isoformat(),
        "validation_status": "INVALID_FOR_VALIDATION",
        "note": args.note,
        "git": git,
        "environment": env,
        "inputs": {"files": files, "price_dir": prices},
    }

    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    with open(os.path.join(out_dir, "data_snapshot.txt"), "w") as f:
        f.write(f"data_snapshot_id: {args.snapshot_id}\n")
        for e in files:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
        f.write(json.dumps(prices, ensure_ascii=False) + "\n")

    print(f"manifest -> {os.path.join(out_dir, 'manifest.json')}")
    print(f"commit={git['commit']} tag={git['tag']} dirty={git['dirty']}")
    print(f"price_dir: {prices.get('n_files')} files, min={prices.get('sample_min_date')} max={prices.get('sample_max_date')}")


if __name__ == "__main__":
    main()
