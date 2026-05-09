"""批量页：统一描述与文案库合并规则（无 Qt 依赖）"""

from src.pro_features.batch.copywriting_helpers import merge_title_desc_from_copywriting_item as _merge_title_desc_from_copywriting_item


def test_apply_all_empty_fills_from_library():
    item = {"short_title": "库标题", "description": "库简介"}
    t, d = _merge_title_desc_from_copywriting_item(
        apply_all=True,
        same_title="",
        same_desc="",
        use_lib_title=True,
        use_lib_desc=True,
        item=item,
    )
    assert t == "库标题"
    assert d == "库简介"


def test_apply_all_library_desc_normalizes_adjacent_topics():
    """文案库简介中连续 #话题 会补空格，便于识别与高亮。"""
    item = {"short_title": "t", "description": "正文#遥马农业#农资店#有机肥"}
    _, d = _merge_title_desc_from_copywriting_item(
        apply_all=True,
        same_title="",
        same_desc="",
        use_lib_title=True,
        use_lib_desc=True,
        item=item,
    )
    assert " #遥马农业 " in d or d.startswith("正文#遥马农业 ")
    from src.domain.publish.work_description import parse_topic_list

    assert parse_topic_list(d) == ["遥马农业", "农资店", "有机肥"]


def test_apply_all_manual_wins_over_library():
    item = {"short_title": "库标题", "description": "库简介"}
    t, d = _merge_title_desc_from_copywriting_item(
        apply_all=True,
        same_title="统一题",
        same_desc="",
        use_lib_title=True,
        use_lib_desc=True,
        item=item,
    )
    assert t == "统一题"
    assert d == "库简介"


def test_apply_all_mixed_manual_and_library():
    item = {"short_title": "库标题", "description": "库简介"}
    t, d = _merge_title_desc_from_copywriting_item(
        apply_all=True,
        same_title="",
        same_desc="统一介",
        use_lib_title=True,
        use_lib_desc=True,
        item=item,
    )
    assert t == "库标题"
    assert d == "统一介"


def test_not_apply_all_only_library_flags():
    item = {"short_title": "A", "description": "B"}
    t, d = _merge_title_desc_from_copywriting_item(
        apply_all=False,
        same_title="忽略",
        same_desc="忽略",
        use_lib_title=True,
        use_lib_desc=False,
        item=item,
    )
    assert t == "A"
    assert d == ""


# ---- _build_task 中 per-video 字段优先于 common 字段 ----

def test_build_task_per_video_overrides_common():
    """video_list 中 per-video 的 title/description/tags 优先于 common_fields 中的。"""
    from src.ui.pages.publish.batch_task_creation_actions import _build_task

    common = {
        "user_id": 1,
        "title": "统一标题",
        "description": "统一描述",
        "tags_str": "统一标签",
        "cover_path": None,
        "poi_info": "",
        "micro_app_info": "",
        "cart_info": "",
        "anchor_info": "",
        "privacy_settings": "{}",
    }
    media = {"file_path": "/v.mp4", "title": "视频标题", "description": "视频描述", "tags": "视频标签"}
    acc = {"platform": "douyin", "platform_username": "u1", "id": 1}

    task = _build_task(acc, media, "10:00", common)
    assert task["title"] == "视频标题"
    assert task["description"] == "视频描述"
    assert task["tags"] == "视频标签"


def test_build_task_empty_per_video_falls_back_to_common():
    """per-video 字段为空时回退到 common_fields。"""
    from src.ui.pages.publish.batch_task_creation_actions import _build_task

    common = {
        "user_id": 1,
        "title": "统一标题",
        "description": "统一描述",
        "tags_str": "统一标签",
        "cover_path": None,
        "poi_info": "",
        "micro_app_info": "",
        "cart_info": "",
        "anchor_info": "",
        "privacy_settings": "{}",
    }
    media = {"file_path": "/v.mp4", "title": "", "description": "", "tags": ""}
    acc = {"platform": "douyin", "platform_username": "u1", "id": 1}

    task = _build_task(acc, media, "10:00", common)
    assert task["title"] == "统一标题"
    assert task["description"] == "统一描述"
    assert task["tags"] == "统一标签"
