"""T-WF-01 Decision Normalization Characterization — 验证 v2 migration 契约能无损承载真实历史数据。

契约来源: docs/RESEARCH_WORKFLOW_LAYER_V2_SCHEMA.md v0.2 §3.4（词级等价映射，自由文本不猜测）
性质: characterization 测试（离线、无网络、不改任何数据文件）
作用: 证明 schema 冻结可承接 data/ledger/decisions.jsonl 真实异构数据（实测 4 种格式并存），
      并为 10-02 后 tools/migrate_decisions_v2.py 提供 reference 契约——该脚本必须与本文件
      的 MIGRATION_MAP / normalize_decision() 对齐（对齐义务: 脚本测试引用本文件）。

真实数据分布（2026-09-03 勘察, 19 条）:
  [15-18] action 字段直通（decision_cli v2 格式, 4 条）
  [0-10]  human_decision.decision（case 卡格式, 11 条: DEEP_RESEARCH×4/WATCH×4/IGNORE×2/IGNORE_ALL×1）
  [11-14] 顶层 decision（overlay 早期混写格式, 4 条: RESEARCH_REQUIRED×2/IGNORE_PENDING/WATCH_RESEARCH）
  decision_type 9 种（relation 保留原值）; created_by 仅 6 条 human（source 派生）
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISIONS = ROOT / "data" / "ledger" / "decisions.jsonl"

# 冻结契约（v0.2 §3.4 + decision_cli ACTIONS 枚举, 与 tools/decision_cli.py 一致）
ACTIONS = {"WATCH", "IGNORE", "BUY_CANDIDATE", "RESEARCH_REQUIRED", "UNKNOWN"}
WORD_MAP = {"buy": "BUY_CANDIDATE", "watch": "WATCH", "pass": "IGNORE"}


def normalize_decision(rec: dict) -> dict:
    """词级等价 normalize（reference 实现 — 未来 migrate 脚本必须对齐）。

    取值优先级（真实分布驱动）:
      1. rec.action 词 ∈ ACTIONS → 直通（decision_cli v2 格式）
      2. rec.human_decision.decision 词 ∈ ACTIONS → 直通（case 卡格式）
      3. rec.decision 词 ∈ ACTIONS → 直通（overlay 早期格式）
      4. 其余自由文本（DEEP_RESEARCH/IGNORE_ALL/IGNORE_PENDING/WATCH_RESEARCH…）→ UNKNOWN,
         不猜测（词不同 ≠ 语义等价; legacy_decision 保留原文）
    relation: decision_type 原值保留（无则 null）; source: created_by 派生（None → UNKNOWN）
    无损: legacy 嵌套保留完整原记录（53 键全量）。
    """
    legacy_decision = None
    raw = rec.get("action") or (rec.get("human_decision") or {}).get("decision") or rec.get("decision")
    if raw is None:
        judgment = "UNKNOWN"
    elif raw in ACTIONS:
        judgment = raw
    elif raw in WORD_MAP:
        judgment = WORD_MAP[raw]
    else:
        judgment = "UNKNOWN"
        legacy_decision = raw

    source = rec.get("created_by")
    norm = {
        "judgment": judgment,
        "relation": rec.get("decision_type"),  # 原值保留, 不归一
        # created_by 存量小写（'human'）→ 大写归一（词级等价, 非语义猜测）; None → UNKNOWN
        "source": (source.upper() if source in ("human", "AI_ASSISTED") else "UNKNOWN"),
        "stock": rec.get("stock"),
        "legacy": rec,
    }
    if legacy_decision is not None:
        norm["legacy_decision"] = legacy_decision
    return norm


def _load_real():
    if not DECISIONS.exists():
        return []
    return [json.loads(l) for l in open(DECISIONS) if l.strip()]


# ---------- 构造数据精确断言（migration 规则本体） ----------

def test_word_map_ledger_schema_values():
    """ledger schema 值词级映射（v0.2 §3.4）: buy/watch/pass → 枚举。"""
    for old, new in [("buy", "BUY_CANDIDATE"), ("watch", "WATCH"), ("pass", "IGNORE")]:
        out = normalize_decision({"decision": old, "stock": "000001"})
        assert out["judgment"] == new, f"{old} 应映射为 {new}"


def test_action_passthrough():
    """decision_cli action 直通（已在枚举内, 同词非猜测）。"""
    out = normalize_decision({"action": "WATCH", "stock": "600338"})
    assert out["judgment"] == "WATCH"
    assert "legacy_decision" not in out


def test_free_text_not_guessed():
    """自由文本不猜测: DEEP_RESEARCH → UNKNOWN + legacy_decision 保留原文。"""
    out = normalize_decision({"decision": "DEEP_RESEARCH", "stock": "300308"})
    assert out["judgment"] == "UNKNOWN"
    assert out["legacy_decision"] == "DEEP_RESEARCH"


def test_overlay_human_state_not_merged():
    """overlay 状态词（IGNORE_PENDING/WATCH_RESEARCH）不映射 judgment（v0.2 §3.3 语义隔离）。"""
    for raw in ("IGNORE_PENDING", "WATCH_RESEARCH", "IGNORE_ALL"):
        out = normalize_decision({"decision": raw, "stock": "600276"})
        assert out["judgment"] == "UNKNOWN", f"{raw} 映射 = 语义猜测, 必须 UNKNOWN"
        assert out["legacy_decision"] == raw


def test_relation_source_derivation():
    """relation = decision_type 原值; source 从 created_by 派生（None 不猜 → UNKNOWN）。"""
    out = normalize_decision({"decision_type": "MODEL_CONFIRM", "created_by": "human",
                              "action": "WATCH", "stock": "605499"})
    assert out["relation"] == "MODEL_CONFIRM"
    assert out["source"] == "HUMAN"
    out2 = normalize_decision({"action": "WATCH", "stock": "605499"})
    assert out2["source"] == "UNKNOWN"


# ---------- 真实数据不变量断言（未来数据增长不脆; 断言规则而非精确值） ----------

def test_real_records_no_loss_and_no_guess():
    """真实 19 条: 每条可 normalize、judgment 合法、UNKNOWN 必带 legacy、非 UNKNOWN 不带。"""
    recs = _load_real()
    assert len(recs) >= 19, "真实 decisions.jsonl 应至少含勘察时的 19 条"
    for rec in recs:
        norm = normalize_decision(rec)
        assert norm["judgment"] in ACTIONS
        if norm["judgment"] == "UNKNOWN":
            assert "legacy_decision" in norm, "UNKNOWN 必须带 legacy_decision（不猜测原则）"
        else:
            assert "legacy_decision" not in norm
        assert norm["relation"] == rec.get("decision_type")
        assert norm["source"] in ("HUMAN", "AI_ASSISTED", "UNKNOWN")


def test_real_records_lossless_legacy():
    """无损: normalized 的 legacy 嵌套必须覆盖原记录全部键（53 键不丢失）。"""
    for rec in _load_real():
        norm = normalize_decision(rec)
        assert set(rec.keys()) <= set(norm["legacy"].keys())
        assert norm["legacy"] is rec or norm["legacy"] == rec


def test_real_records_unknown_floor():
    """现状钉住: 勘察时 19 条中 7 条落 UNKNOWN（DEEP_RESEARCH×4+IGNORE_ALL+IGNORE_PENDING+
    WATCH_RESEARCH）。下限断言——规则收紧（UNKNOWN 减少）必须显式更新本测试。"""
    recs = _load_real()
    unknowns = sum(1 for r in recs if normalize_decision(r)["judgment"] == "UNKNOWN")
    assert unknowns >= 7, f"勘察基线 UNKNOWN=7, 实测 {unknowns}（减少=规则变更, 需更新测试）"


def test_original_file_untouched():
    """normalize 是派生视图: 测试自身不修改原文件（读取前后 size 一致）。"""
    before = os.path.getsize(DECISIONS) if DECISIONS.exists() else None
    _ = [normalize_decision(r) for r in _load_real()]
    after = os.path.getsize(DECISIONS) if DECISIONS.exists() else None
    assert before == after
