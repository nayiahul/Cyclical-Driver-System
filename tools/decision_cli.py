"""Decision CLI — 极简判断留痕（v2: 30 秒/条）。

设计原则 (2026-09-03 收敛):
- 投资判断发生在脑子里, 不发生在命令行 — 输入必须 30 秒完成
- 最小必填: 动作 / 一句话判断 / 反证 / 验证节点
- 可选: 置信度(默认MEDIUM) / 备注
- 输出: data/ledger/decisions.jsonl (追加)

用法:
  python tools/decision_cli.py --book output/research_book_YYYYMMDD.csv
  python tools/decision_cli.py --stock 600338   # 指定单只
  python tools/decision_cli.py --quick 600338,WATCH,"锌价驱动但周期未消","若锌价续涨则低估成立","Q3"
"""
import argparse
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "data", "ledger", "decisions.jsonl")
ACTIONS = ["WATCH", "IGNORE", "BUY_CANDIDATE", "RESEARCH_REQUIRED", "UNKNOWN"]


def save(rec: dict):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"✅ 已记录: {rec['stock']} | {rec['action']}")


def interactive(stock: str, name: str = "", context: str = ""):
    """极简交互: 每字段一行输入, 回车跳过可选。"""
    print(f"\n{'='*50}")
    print(f"{stock} {name}")
    if context:
        print(f"  {context[:120]}")
    print(f"{'='*50}")

    # 1. 动作 (必填)
    print(f"动作 ({'/'.join(ACTIONS)}):")
    action = input("> ").strip().upper()
    if action not in ACTIONS:
        action = "UNKNOWN"

    # 2. 一句话判断 (必填)
    thesis = input("判断(一句话) > ").strip()
    while not thesis:
        thesis = input("判断不能为空 > ").strip()

    # 3. 反证 (必填 — 恒瑞教训)
    counter = input("反证(什么情况我错?) > ").strip()
    while not counter:
        counter = input("反证不能为空 > ").strip()

    # 4. 验证节点 (可选, 默认 Q3)
    check = input("验证节点(默认Q3) > ").strip() or "Q3"

    # 5. 置信度 (可选)
    conf = input("置信度 H/M/L(默认M) > ").strip().upper()
    conf = conf if conf in ("H", "M", "L") else "M"

    save({
        "stock": stock, "name": name, "action": action,
        "thesis": thesis, "counter": counter, "check": check,
        "confidence": conf, "date": datetime.now().strftime("%Y-%m-%d"),
        "created_at": datetime.now().isoformat(),
        "status": "PENDING_VALIDATION",
    })


def main():
    ap = argparse.ArgumentParser(description="极简判断留痕")
    ap.add_argument("--book", help="研究书 CSV (逐只提示)")
    ap.add_argument("--stock", help="指定代码")
    ap.add_argument("--name", default="")
    ap.add_argument("--quick", help="快速模式: code,ACTION,判断,反证,验证")
    args = ap.parse_args()

    # 快速模式: 单条命令完成
    if args.quick:
        parts = [p.strip() for p in args.quick.split(",")]
        if len(parts) >= 4:
            stock, action, thesis, counter = parts[0], parts[1].upper(), parts[2], parts[3]
            check = parts[4] if len(parts) > 4 else "Q3"
            if action not in ACTIONS:
                print(f"❌ 动作必须是 {ACTIONS}")
                return
            save({"stock": stock, "name": args.name, "action": action,
                  "thesis": thesis, "counter": counter, "check": check,
                  "confidence": "M", "date": datetime.now().strftime("%Y-%m-%d"),
                  "created_at": datetime.now().isoformat(),
                  "status": "PENDING_VALIDATION"})
            return

    # Book 模式: 逐只(可中断)
    if args.book:
        import pandas as pd
        df = pd.read_csv(args.book)
        df["code"] = df["code"].astype(str).str.zfill(6)
        done = set()
        if os.path.exists(LEDGER):
            for line in open(LEDGER):
                try:
                    done.add(json.loads(line)["stock"])
                except Exception:
                    pass
        for _, row in df.head(20).iterrows():
            code = row["code"]
            if code in done:
                continue
            try:
                interactive(code, context=f"{row.get('research_stage','')} | {str(row.get('drivers',''))[:80]}")
            except (KeyboardInterrupt, EOFError):
                print("\n已中断, 已记录保留")
                return
        print("\n完成 (可 --book 继续, 自动跳过已录)")
        return

    if args.stock:
        interactive(args.stock, args.name)
        return

    ap.print_help()


if __name__ == "__main__":
    main()
