"""Human Validation Overlay — 人工结论叠加层 (Phase 1, 不改主状态)。

设计原则 (2026-09-03 讨论):
- 机器状态(Machine Signal)与人工状态(Human State)分离, 互不覆盖
- Overlay 只叠加不修改: A 级保留(机器发现异常), IGNORE 并行(人的投资判断)
- 记录迁移历史 (state_transition_log) — 未来 State Change 的数据基础
- 不改模型/评分/主池; Phase 2 (T+30) 再决定是否升级

数据:
  data/overlay/state.yaml      当前状态
  data/overlay/transitions.jsonl  迁移历史

用法:
  python tools/validation_overlay.py --status        # 查看全部
  python tools/validation_overlay.py --add 600276 --machine L1_Growth_A \
      --human IGNORE_PENDING --signal_type LOW_BASE_BIAS --evidence "CAL-001"
"""
import argparse
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVERLAY_DIR = os.path.join(ROOT, "data", "overlay")
STATE_FILE = os.path.join(OVERLAY_DIR, "state.yaml")
TRANS_FILE = os.path.join(OVERLAY_DIR, "transitions.jsonl")

# Signal Type 分类 (来自 CAL 系列教训, 非评分)
SIGNAL_TYPES = [
    "LOW_BASE_BIAS",        # 低基数同比 (CAL-001)
    "CYCLE_BETA",           # 商品/周期驱动 (CAL-003)
    "QUALITY_GROWTH",       # 真实高质量增长 (CAL-004 旭创)
    "QUALITY_VALUATION",    # 好公司×价格问题 (CAL-004)
    "VALUATION_COMPRESSION",# 估值压缩型
    "MACRO_RELATED",        # 宏观驱动 (MAC-001)
    "POLICY_RISK",          # 政策风险 (FCC类)
    "UNCLASSIFIED",
]


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    # yaml 简化读取 (项目内无 yaml 依赖要求, 用 dict 序列化替代)
    try:
        import yaml
        with open(STATE_FILE) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # fallback: 简易嵌套解析
        state, cur = {}, None
        for line in open(STATE_FILE):
            line = line.rstrip()
            if not line.strip() or line.strip().startswith("#"):
                continue
            if not line.startswith(" ") and line.endswith(":"):
                cur = line[:-1].strip()
                state[cur] = {}
            elif cur and ":" in line:
                k, v = line.split(":", 1)
                state[cur][k.strip()] = v.strip().strip("'\"")
        return state


def save_state(state: dict):
    os.makedirs(OVERLAY_DIR, exist_ok=True)
    lines = ["# Human Validation Overlay — 人工结论叠加 (机器状态 并行 人工状态)\n"]
    for code, info in sorted(state.items()):
        lines.append(f"{code}:")
        for k, v in info.items():
            lines.append(f"  {k}: {v}")
    with open(STATE_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")


def log_transition(code: str, machine: str, human: str, sig_type: str,
                   evidence: str, author: str = "human"):
    os.makedirs(OVERLAY_DIR, exist_ok=True)
    rec = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "code": code, "machine": machine, "human": human,
        "signal_type": sig_type, "evidence": evidence, "author": author,
    }
    with open(TRANS_FILE, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Human Validation Overlay")
    ap.add_argument("--status", action="store_true", help="查看全部 overlay")
    ap.add_argument("--add", metavar="CODE", help="添加/更新标的")
    ap.add_argument("--machine", default="", help="机器状态 (如 L1_Growth_A)")
    ap.add_argument("--human", default="", help="人工状态 (如 IGNORE_PENDING)")
    ap.add_argument("--signal_type", default="UNCLASSIFIED", choices=SIGNAL_TYPES)
    ap.add_argument("--evidence", default="", help="证据/依据 (如 CAL-001)")
    args = ap.parse_args()

    state = load_state()

    if args.status:
        if not state:
            print("Overlay 为空 (尚无人工结论回写)")
        for code, info in state.items():
            print(f"{code}:")
            for k, v in info.items():
                print(f"  {k}: {v}")
        # 显示迁移历史
        if os.path.exists(TRANS_FILE):
            print("\n迁移历史:")
            for line in open(TRANS_FILE):
                r = json.loads(line)
                print(f"  {r['date']} {r['code']}: {r['machine']} → {r['human']} ({r['signal_type']})")
        return

    if args.add:
        info = state.get(args.add, {})
        # 保留历史机器状态, 叠加新人工状态
        prev_machine = info.get("machine", args.machine or "UNKNOWN")
        prev_human = info.get("human", "-")
        info.update({
            "machine": args.machine or prev_machine,
            "human": args.human or prev_human,
            "signal_type": args.signal_type,
            "evidence": args.evidence,
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        state[args.add] = info
        save_state(state)
        if prev_human != info["human"]:
            log_transition(args.add, prev_machine, info["human"],
                           args.signal_type, args.evidence)
        print(f"✅ Overlay 更新: {args.add}")
        print(f"   Machine: {info['machine']}")
        print(f"   Human:   {info['human']}")
        print(f"   Type:    {args.signal_type}")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
