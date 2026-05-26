# -*- coding: utf-8 -*-
"""快手步骤 4 作品描述/话题预处理单元测试"""

from __future__ import annotations

import pytest

from src.plugins.community.kuaishou.steps.step_04_description import (
    MetadataFillStep,
    _normalize_collected_topic,
    _topic_in_collected,
    _topic_label_for_type,
)

pytestmark = pytest.mark.unit


class TestTopicLabel:
    def test_strip_hash_and_fullwidth(self):
        assert _topic_label_for_type("#西瓜种植") == "西瓜种植"
        assert _topic_label_for_type("\uff03快乐") == "快乐"


class TestTopicCollected:
    def test_normalize_collected_strips_hash(self):
        assert _normalize_collected_topic("# 西瓜种植") == "西瓜种植"

    def test_topic_in_collected(self):
        formed = ["西瓜种植", "水溶肥定制"]
        assert _topic_in_collected("西瓜种植", formed)
        assert _topic_in_collected("#西瓜种植", formed)
        assert not _topic_in_collected("遥马农业", formed)


class TestBuildDescriptionWithTopicLimit:
    def test_strip_topics_from_body(self):
        step = MetadataFillStep()
        body, kept, total = step._build_description_with_topic_limit(
            "想做西瓜专用肥 #西瓜种植 #水溶肥定制",
            [],
        )
        assert "西瓜种植" in kept
        assert "水溶肥定制" in kept
        assert "#" not in body
        assert "想做西瓜专用肥" in body
        assert total == 2

    def test_merge_tags_and_cap_at_four(self):
        step = MetadataFillStep()
        body, kept, total = step._build_description_with_topic_limit(
            "#甲 #乙",
            ["丙", "丁", "戊"],
        )
        assert total == 5
        assert len(kept) == 4
        assert kept == ["甲", "乙", "丙", "丁"]
        assert "#" not in body

    def test_fullwidth_hash_in_description(self):
        step = MetadataFillStep()
        fw = "\uff03"
        body, kept, total = step._build_description_with_topic_limit(
            f"正文{fw}遥马农业{fw}农资店",
            [],
        )
        assert kept == ["遥马农业", "农资店"]
        assert total == 2
        assert "遥马农业" not in body
