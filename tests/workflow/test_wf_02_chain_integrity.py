"""T-WF-02 ID Chain Integrity Characterization — 钉住 v2 id 链现状（断链点清单测试化）。

契约来源: docs/RESEARCH_WORKFLOW_LAYER_V2_SCHEMA.md v0.2 §2（完整数据链）:
  Thesis(thesis_id) → Signal(signal_id) → Task(task_id) → Decision(decision_id)
  → Outcome(outcome_id) → ThesisReview
性质: characterization 测试（离线、无网络、不改任何文件）
作用: 把 v0.2 断链点清单（thesis 无 id、decision 无 task_id、outcome 不挂 thesis）钉成可执行断言。
      10-02 后 Phase 0/1 实现关闭缺口时, 对应断言 RED→GREEN 翻转, 测试同步更新。

真实路径事实（2026-09-03 勘察, 与 v0.2 §1.3 文档标注差异——文档写 data/ledger/, 实际在
data/ledger_historical/; 本测试按真实路径钉住）:
  data/ledger/decisions.jsonl          19 条（53 键异构, 无 task_id）
  data/ledger_historical/outcomes.jsonl 100 条（100/100 有 outcome_id, 0 含 thesis_id）
  data/ledger_historical/reviews.jsonl  100 条（100/100 review_id + outcome 引用闭包 100%）
  data/thesis/*.yaml                    2 张卡（0 含 thesis_id/scope/status）
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISIONS = ROOT / "data" / "ledger" / "decisions.jsonl"
OUTCOMES = ROOT / "data" / "ledger_historical" / "outcomes.jsonl"
REVIEWS = ROOT / "data" / "ledger_historical" / "reviews.jsonl"
THESIS_DIR = ROOT / "data" / "thesis"


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in open(path) if l.strip()]


def _thesis_has_key(path: Path, key: str) -> bool:
    """yaml 行扫描（项目内无 pyyaml 依赖）: 仅顶层键（无前导空格）——
    嵌套键（如 assumption 级 status）不视为顶层。"""
    for line in open(path):
        if line[:1] in (" ", "\t"):
            continue  # 嵌套键, 跳过
        s = line.strip()
        if s.startswith("#") or not s:
            continue
        if s.startswith(key + ":"):
            return True
    return False


# ---------- 链上已存在的环节（正断言, 10-02 后不得回退） ----------

def test_outcome_chain_exists():
    """Outcome 层: 100/100 有 outcome_id（链的 backbone 存在）。"""
    outs = _load(OUTCOMES)
    assert len(outs) == 100
    assert all(r.get("outcome_id") for r in outs)


def test_review_chain_closed():
    """Review 层引用闭包: 100/100 review 的 outcome_id 能在 outcomes 中找到（现有最完整的链）。"""
    revs, outs = _load(REVIEWS), _load(OUTCOMES)
    ids = {r["outcome_id"] for r in outs}
    assert len(revs) == 100
    assert all(r.get("review_id") for r in revs)
    assert all(r.get("outcome_id") in ids for r in revs), "review→outcome 引用断链"


# ---------- 断链点清单（现状钉住, Phase 0/1 关闭时翻转） ----------

def test_thesis_gap_pinned():
    """断链点 1: 2 张 thesis 卡均无 thesis_id/scope/status（v0.2 §1.1 补字段缺口）。"""
    cards = sorted(THESIS_DIR.glob("*.yaml"))
    assert len(cards) == 2, f"thesis 卡数量变化: {[c.name for c in cards]}"
    for card in cards:
        assert not _thesis_has_key(card, "thesis_id"), f"{card.name} 已补 thesis_id → 更新本测试"
        assert not _thesis_has_key(card, "scope")
        assert not _thesis_has_key(card, "status")


def test_decision_task_gap_pinned():
    """断链点 2: decisions.jsonl 无任何 task_id（v2 关联字段缺口）。"""
    recs = _load(DECISIONS)
    assert len(recs) >= 19
    assert all("task_id" not in r for r in recs), "出现 task_id → Phase 0 已落地, 更新本测试"


def test_outcome_thesis_gap_pinned():
    """断链点 3: outcomes 100 条均不挂 thesis_id（v0.2 §2 可选字段缺口）。"""
    outs = _load(OUTCOMES)
    assert all("thesis_id" not in r for r in outs), "outcome 挂 thesis_id → 更新本测试"


def test_signal_layer_absent():
    """断链点 4: signal 层尚不存在（v0.2 §4.4 预留; data/signals/ 目录未建）。"""
    assert not (ROOT / "data" / "signals").exists()


def test_task_events_absent():
    """断链点 5: task_events.jsonl 尚不存在（v0.2 §3.2 新建文件, Phase 0 产物）。"""
    assert not (ROOT / "data" / "ledger" / "task_events.jsonl").exists()
