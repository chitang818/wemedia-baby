from __future__ import annotations

import pytest

from src.plugins.pro.xiaohongshu._xhs_submit_probe import (
    is_shadow_submit_candidate_text,
    pick_primary_host,
    summarize_snapshot_for_log,
    url_indicates_publish_success,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("定时发布", True),
        ("发布", True),
        ("暂存离开", False),
        ("保存草稿", False),
        ("", False),
    ],
)
def test_is_shadow_submit_candidate_text(text: str, expected: bool) -> None:
    assert is_shadow_submit_candidate_text(text) is expected


def test_pick_primary_host_prefers_is_publish() -> None:
    snap = {
        "hosts": [
            {"isPublish": "", "submitText": "发布"},
            {"isPublish": "true", "submitText": "定时发布"},
        ],
    }
    assert pick_primary_host(snap)["submitText"] == "定时发布"


def test_summarize_snapshot_for_log() -> None:
    snap = {
        "pickerOpen": True,
        "focusInSchedule": True,
        "schedule": {"checkboxChecked": True},
        "hostCount": 1,
        "hosts": [
            {
                "isPublish": "true",
                "submitText": "定时发布",
                "submitDisabled": "true",
                "hasSr": True,
                "shadowButtonCount": 2,
                "shadowButtons": [
                    {"text": "暂存离开", "className": "ce-btn white", "width": 80, "height": 32},
                    {"text": "定时发布", "className": "ce-btn bg-red", "width": 100, "height": 32},
                ],
            },
        ],
    }
    s = summarize_snapshot_for_log(snap)
    assert s["submit_text"] == "定时发布"
    assert s["submit_disabled"] is True
    assert s["has_sr"] is True
    assert s["schedule_picker_open"] is True


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://creator.xiaohongshu.com/publish/success", True),
        ("https://creator.xiaohongshu.com/publish/publish?published=true", True),
        (
            "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video",
            False,
        ),
        ("https://creator.xiaohongshu.com/new/note/manage", True),
    ],
)
def test_url_indicates_publish_success(url: str, expected: bool) -> None:
    assert url_indicates_publish_success(url) is expected
