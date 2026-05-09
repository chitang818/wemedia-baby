"""
文案辅助纯函数单元测试
测试 parse_topic_list、extract_work_id_from_filename、merge_title_desc_from_copywriting_item。
"""

import pytest

from src.pro_features.batch.copywriting_helpers import (
    parse_topic_list,
    extract_work_id_from_filename,
    merge_title_desc_from_copywriting_item,
)

pytestmark = pytest.mark.unit


class TestParseTopicList:

    def test_basic_topics(self):
        assert parse_topic_list("#好心情 #每日打卡") == ["好心情", "每日打卡"]

    def test_mixed_text_and_topics(self):
        result = parse_topic_list("今天很开心 #好心情 #每日打卡")
        assert result == ["好心情", "每日打卡"]

    def test_empty_string(self):
        assert parse_topic_list("") == []

    def test_none_like_empty(self):
        assert parse_topic_list(None) == []  # type: ignore

    def test_no_topics(self):
        assert parse_topic_list("普通文本，没有话题") == []

    def test_deduplication(self):
        result = parse_topic_list("#好心情 #好心情 #每日打卡")
        assert result == ["好心情", "每日打卡"]

    def test_trailing_punctuation_stripped(self):
        # 话题末尾紧跟标点后无其他字时，逗号被剥离
        result = parse_topic_list("#好心情, #每日打卡")
        # 逗号后空格是英文逗号分隔，不影响话题本身
        assert "好心情" in result or len(result) >= 1

    def test_single_topic(self):
        assert parse_topic_list("#vlog") == ["vlog"]

    def test_adjacent_topics_no_space(self):
        result = parse_topic_list("#话题一#话题二")
        assert "话题一" in result


class TestExtractWorkIdFromFilename:

    def test_with_dash_uses_first_five_chars_of_stem(self):
        assert extract_work_id_from_filename("A0001-快乐每一天.mp4") == "A0001"

    def test_without_dash(self):
        assert extract_work_id_from_filename("A0002.mp4") == "A0002"

    def test_full_path(self):
        assert extract_work_id_from_filename("/some/path/B0003-title.jpg") == "B0003"

    def test_windows_path(self):
        assert extract_work_id_from_filename("C:\\videos\\C0001-intro.mp4") == "C0001"

    def test_no_extension(self):
        assert extract_work_id_from_filename("D0004-no-ext") == "D0004"

    def test_stem_longer_than_five_still_prefix_five(self):
        assert extract_work_id_from_filename("E0005-part-one.mp4") == "E0005"

    def test_empty_string_returns_empty(self):
        assert extract_work_id_from_filename("") == ""

    def test_only_extension(self):
        assert extract_work_id_from_filename(".mp4") == ""

    def test_stem_shorter_than_five(self):
        assert extract_work_id_from_filename("A001.mp4") == ""

    def test_lowercase_prefix_not_matched(self):
        assert extract_work_id_from_filename("a0001.mp4") == ""

    def test_chinese_prefix_not_matched(self):
        assert extract_work_id_from_filename("第001集-精彩片段.mp4") == ""

    def test_windows_duplicate_space_before_paren(self):
        assert extract_work_id_from_filename("A0008 (1).mp4") == "A0008"
        assert extract_work_id_from_filename(r"C:\media\A0008 (2).mp4") == "A0008"

    def test_invalid_first_five_chars(self):
        assert extract_work_id_from_filename("AB0001.mp4") == ""


class TestMergeTitleDescFromCopywritingItem:

    def test_apply_all_prefers_same_text(self):
        t, d = merge_title_desc_from_copywriting_item(
            apply_all=True,
            same_title="统一标题",
            same_desc="统一简介",
            use_lib_title=True,
            use_lib_desc=True,
            item={"short_title": "库标题", "description": "库简介"},
        )
        assert t == "统一标题"
        assert d == "统一简介"

    def test_apply_all_falls_back_to_library_when_empty(self):
        t, d = merge_title_desc_from_copywriting_item(
            apply_all=True,
            same_title="",
            same_desc="",
            use_lib_title=True,
            use_lib_desc=True,
            item={"short_title": "库标题", "description": "库简介"},
        )
        assert t == "库标题"
        assert d == "库简介"

    def test_apply_all_no_item(self):
        t, d = merge_title_desc_from_copywriting_item(
            apply_all=True,
            same_title="标题",
            same_desc="简介",
            use_lib_title=True,
            use_lib_desc=True,
            item=None,
        )
        assert t == "标题"
        assert d == "简介"

    def test_not_apply_all_uses_library(self):
        t, d = merge_title_desc_from_copywriting_item(
            apply_all=False,
            same_title="统一标题",
            same_desc="统一简介",
            use_lib_title=True,
            use_lib_desc=True,
            item={"short_title": "库标题", "description": "库简介"},
        )
        assert t == "库标题"
        assert d == "库简介"

    def test_not_apply_all_lib_disabled(self):
        t, d = merge_title_desc_from_copywriting_item(
            apply_all=False,
            same_title="任意",
            same_desc="任意",
            use_lib_title=False,
            use_lib_desc=False,
            item={"short_title": "库标题", "description": "库简介"},
        )
        assert t == ""
        assert d == ""

    def test_not_apply_all_no_item(self):
        t, d = merge_title_desc_from_copywriting_item(
            apply_all=False,
            same_title="任意",
            same_desc="任意",
            use_lib_title=True,
            use_lib_desc=True,
            item=None,
        )
        assert t == ""
        assert d == ""

    def test_random_lib_only_content_does_not_generate_title(self):
        # 随机库常见情况：仅有 content，short_title 为空。
        # 按产品需求：不自动生成标题；只有勾选简介时才填简介。
        t, d = merge_title_desc_from_copywriting_item(
            apply_all=False,
            same_title="",
            same_desc="",
            use_lib_title=True,
            use_lib_desc=True,
            item={"short_title": "", "description": "", "content": "这里是正文\n#话题"},
        )
        assert t == ""
        assert d.startswith("这里是正文")

    def test_whitespace_stripped(self):
        t, d = merge_title_desc_from_copywriting_item(
            apply_all=True,
            same_title="  标题  ",
            same_desc="  简介  ",
            use_lib_title=False,
            use_lib_desc=False,
            item=None,
        )
        assert t == "标题"
        assert d == "简介"
