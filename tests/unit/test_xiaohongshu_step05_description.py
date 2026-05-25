# -*- coding: utf-8 -*-
"""小红书步骤5：正文/话题拆分与话题输入策略单元测试。"""

from __future__ import annotations

import pytest

from src.plugins.pro.xiaohongshu.steps.step_05_description import (
    _distinct_normalized_topics,
    _merge_editor_topic_names,
    _normalize_editor_topic_name,
    _split_body_and_topics,
    _topic_count_in_text,
    _topic_label_for_type,
    _topic_label_in_collected,
    _topic_pause_ms,
    _topic_type_delay,
    _truncate_topics_to_limit,
    should_use_topic_entry_btn,
)

pytestmark = pytest.mark.unit


class TestTopicTiming:
    def test_type_delay_faster_than_body_default(self):
        assert _topic_type_delay(1.0) < 50

    def test_pause_scales_with_speed_rate(self):
        assert _topic_pause_ms(400, 2.0) > _topic_pause_ms(400, 0.5)


class TestTopicLabelForType:
    def test_strips_single_hash(self):
        assert _topic_label_for_type("#蔬菜种植") == "蔬菜种植"

    def test_strips_double_hash(self):
        assert _topic_label_for_type("##鸭血水溶肥") == "鸭血水溶肥"

    def test_plain_label(self):
        assert _topic_label_for_type("大田作物") == "大田作物"


class TestShouldUseTopicEntryBtn:
    def test_first_topic_always_uses_btn_when_not_compose(self):
        assert should_use_topic_entry_btn(0, False) is True
        assert should_use_topic_entry_btn(0, True) is True

    def test_second_topic_skips_btn_when_in_compose(self):
        assert should_use_topic_entry_btn(1, True) is False

    def test_second_topic_uses_btn_when_not_compose(self):
        assert should_use_topic_entry_btn(1, False) is True


class TestMergeEditorTopics:
    def test_dom_names_without_hash_in_inner_text(self):
        inner = "正文提高！"
        dom = ["蔬菜种植", "转色增甜", "鸭血水溶肥"]
        merged = _merge_editor_topic_names(dom, inner)
        assert merged == ["蔬菜种植", "转色增甜", "鸭血水溶肥"]

    def test_merge_dedupes_dom_and_text(self):
        inner = "结尾 #大田作物"
        dom = ["蔬菜种植", "大田作物"]
        merged = _merge_editor_topic_names(dom, inner)
        assert merged == ["蔬菜种植", "大田作物"]

    def test_normalize_xhs_compose_suffix(self):
        assert _normalize_editor_topic_name("蔬菜种植[话题]#") == "蔬菜种植"
        assert _normalize_editor_topic_name("转色增甜[话题]") == "转色增甜"

    def test_label_in_collected_with_compose_suffix(self):
        raw = ["蔬菜种植[话题]#", "蔬菜种植[话题]"]
        assert _topic_label_in_collected("蔬菜种植", raw)
        assert _distinct_normalized_topics(raw) == ["蔬菜种植"]


class TestTopicCountInText:
    def test_counts_distinct_topics(self):
        text = "正文 #蔬菜种植 #蔬菜种植 #转色增甜"
        assert _topic_count_in_text(text) == 2

    def test_five_topics(self):
        text = (
            "提高！#蔬菜种植 #转色增甜 #鸭血水溶肥 #大田作物 #遥马农业"
        )
        assert _topic_count_in_text(text) == 5


class TestTruncateTopics:
    def test_no_truncation(self):
        topics, truncated = _truncate_topics_to_limit(["a", "b"], 10)
        assert topics == ["a", "b"]
        assert truncated is False

    def test_truncates_to_limit(self):
        topics, truncated = _truncate_topics_to_limit(["a", "b", "c"], 2)
        assert topics == ["a", "b"]
        assert truncated is True


class TestSplitBodyAndTopics:
    def test_adjacent_topics_split_and_body_stripped(self):
        desc = "正文提高！#蔬菜种植#转色增甜#鸭血水溶肥"
        body, topics = _split_body_and_topics(desc, [])
        assert "#" not in body
        assert "正文提高" in body
        assert topics == ["蔬菜种植", "转色增甜", "鸭血水溶肥"]

    def test_merge_tags_not_in_description(self):
        desc = "只有正文 #已有话题"
        body, topics = _split_body_and_topics(desc, ["追加话题", "#已有话题"])
        assert "追加话题" in topics
        assert "已有话题" in topics
        assert topics.count("已有话题") == 1

    def test_empty_description_only_tags(self):
        body, topics = _split_body_and_topics("", ["标签A", "标签B"])
        assert body == ""
        assert topics == ["标签A", "标签B"]

    def test_five_topics_from_preset_like_description(self):
        desc = (
            "辣椒上色慢、色泽差？鸭血肥，转色均匀色泽亮，精品椒率直接提高！"
            "#蔬菜种植#转色增甜#鸭血水溶肥#大田作物#遥马农业"
        )
        body, topics = _split_body_and_topics(desc, [])
        assert "大田作物" in topics
        assert "遥马农业" in topics
        assert len(topics) == 5
        assert "#" not in body
