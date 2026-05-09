"""
作品简介 #话题 解析模块单元测试（与单任务页、批量文案共用规则）。
"""

from __future__ import annotations

import pytest

from src.domain.publish.work_description import (
    normalize_topics_for_paste,
    parse_topic_list,
    parse_topic_ranges,
    strip_topic_trailing_punctuation,
)

pytestmark = pytest.mark.unit


class TestParseTopicList:

    def test_basic_topics(self):
        result = parse_topic_list("#好心情 #每日打卡")
        assert "好心情" in result
        assert "每日打卡" in result

    def test_empty_string(self):
        assert parse_topic_list("") == []

    def test_none_returns_empty(self):
        assert parse_topic_list(None) == []

    def test_no_topics(self):
        assert parse_topic_list("普通文本") == []

    def test_deduplication(self):
        result = parse_topic_list("#重复 #重复 #不同")
        assert result.count("重复") == 1

    def test_trailing_punctuation_stripped(self):
        result = parse_topic_list("#好心情 今天开心")
        for tag in result:
            assert not tag.endswith(" ")

    def test_topic_at_end(self):
        result = parse_topic_list("描述文字 #结尾话题")
        assert "结尾话题" in result

    def test_adjacent_topics_no_space(self):
        # 与单页规则一致：相邻 #话题 分别识别
        result = parse_topic_list("#话题一#话题二")
        assert "话题一" in result
        assert "话题二" in result

    def test_fullwidth_hash_as_separator(self):
        # 全角 ＃（Excel/文案库常见）须与半角 # 一样拆成多个话题
        fw = "\uff03"
        s = f"正文{fw}遥马农业{fw}农资店{fw}有机肥"
        assert parse_topic_list(s) == ["遥马农业", "农资店", "有机肥"]

    def test_mixed_ascii_and_fullwidth_hash(self):
        fw = "\uff03"
        s = f"#遥马农业{fw}农资店#有机肥"
        assert parse_topic_list(s) == ["遥马农业", "农资店", "有机肥"]

    def test_normalize_inserts_space_between_adjacent_topics(self):
        s = "#a#b#c"
        n = normalize_topics_for_paste(s)
        assert parse_topic_list(n) == ["a", "b", "c"]
        assert "#a #" in n and "#b #" in n

    def test_topic_stops_at_punctuation(self):
        result = parse_topic_list("#我好快乐,你在哪")
        assert result == ["我好快乐"]

    def test_three_topics_split_by_spaces(self):
        result = parse_topic_list("#中国 #美国 #韩国")
        assert result == ["中国", "美国", "韩国"]


class TestParseTopicRanges:

    def test_returns_list_of_tuples(self):
        ranges = parse_topic_ranges("#话题一 #话题二")
        assert isinstance(ranges, list)
        assert len(ranges) == 2
        for r in ranges:
            assert isinstance(r, tuple)
            assert len(r) == 2

    def test_empty_string_returns_empty(self):
        assert parse_topic_ranges("") == []

    def test_range_values_valid(self):
        text = "#话题 后面文字"
        ranges = parse_topic_ranges(text)
        for start, end in ranges:
            assert 0 <= start < end <= len(text)


class TestStripTopicTrailingPunctuation:

    def test_strips_chinese_period(self):
        result = strip_topic_trailing_punctuation("#话题。")
        assert result == "#话题"

    def test_strips_exclamation(self):
        result = strip_topic_trailing_punctuation("#话题！")
        assert result == "#话题"

    def test_keeps_clean_topic(self):
        result = strip_topic_trailing_punctuation("#好心情")
        assert result == "#好心情"

    def test_no_hash_returns_as_is(self):
        result = strip_topic_trailing_punctuation("普通文本")
        assert result == "普通文本"


class TestNormalizeTopicsForPaste:

    def test_no_topics_returned_as_is(self):
        text = "没有话题的文本"
        assert normalize_topics_for_paste(text) == text

    def test_adds_space_after_topic(self):
        result = normalize_topics_for_paste("#话题文字")
        assert isinstance(result, str)

    def test_adds_space_after_topic_in_paste(self):
        result = normalize_topics_for_paste("#话题其他文字")
        assert isinstance(result, str)

    def test_empty_string(self):
        assert normalize_topics_for_paste("") == ""
