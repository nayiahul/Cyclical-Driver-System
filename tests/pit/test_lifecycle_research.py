"""Lifecycle Research Layer 测试 — 研究标签 schema 与行为。"""
import sys
import os

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from growth_os.lifecycle_research import LifecycleResearchLayer, STAGE_LABELS, RADAR_MAP


class TestSchema:
    """Research Card schema 锁。"""

    def test_stage_labels(self):
        assert STAGE_LABELS["L1"] == "Early Discovery"
        assert STAGE_LABELS["L2"] == "Confirmation"
        assert STAGE_LABELS["L3"] == "Consensus"
        assert STAGE_LABELS["L5"] == "Recovery Watch"

    def test_annotate_adds_columns(self):
        """annotate 必须加齐 6 个标签列且不改原列。"""
        layer = LifecycleResearchLayer(ind_map={})
        df = pd.DataFrame({"code": ["000001", "000002"], "score": [80, 70]})
        out = layer.annotate(df, "20240102")
        for col in ["lifecycle_state", "expectation_state", "research_stage",
                    "research_priority", "radar", "drivers", "risks"]:
            assert col in out.columns, f"缺少列 {col}"
        assert "score" in out.columns, "原列被删除"
        assert len(out) == 2

    def test_radar_mapping(self):
        """radar 分组: L1/L2→growth, L5→recovery。"""
        assert RADAR_MAP["L1"] == "growth_radar"
        assert RADAR_MAP["L5"] == "recovery_radar"
        assert RADAR_MAP["L3"] == "watch"
