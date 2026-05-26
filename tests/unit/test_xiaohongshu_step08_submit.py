from __future__ import annotations

import pytest

from src.plugins.pro.xiaohongshu._xhs_submit_probe import url_indicates_publish_success
from src.plugins.pro.xiaohongshu.steps.step_08_submit import (
    _MAX_READY_BTN_SEC,
    _MAX_READY_BTN_SEC_SCHEDULED,
    _SUBMIT_TEXT_IMMEDIATE,
    _SUBMIT_TEXT_SCHEDULED,
    _format_submit_timeout_message,
    _is_scheduled_submit_mode,
    _is_xhs_publish_edit_url,
    _labels_for_submit_text,
    _max_ready_btn_sec,
    _should_full_unlock_on_poll,
    _submit_button_labels,
    _url_indicates_success,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://creator.xiaohongshu.com/publish/publish?target=video",
            True,
        ),
        (
            "https://creator.xiaohongshu.com/publish/publish?source=&published=true",
            False,
        ),
        (
            "https://creator.xiaohongshu.com/publish/success",
            False,
        ),
        (
            "https://creator.xiaohongshu.com/new/note/manage",
            False,
        ),
        ("", False),
    ],
)
def test_is_xhs_publish_edit_url(url: str, expected: bool) -> None:
    assert _is_xhs_publish_edit_url(url) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://creator.xiaohongshu.com/new/note/manage", True),
        ("https://creator.xiaohongshu.com/publish/success?source=1", True),
        (
            "https://creator.xiaohongshu.com/publish/publish?source=&published=true",
            True,
        ),
        (
            "https://creator.xiaohongshu.com/publish/publish?target=video",
            False,
        ),
        ("https://example.com/", False),
    ],
)
def test_url_indicates_success(url: str, expected: bool) -> None:
    assert _url_indicates_success(url) is expected
    assert url_indicates_publish_success(url) is expected


def test_submit_button_labels_scheduled_metadata() -> None:
    labels = _submit_button_labels({"schedule_time": "2026-05-26 14:07"})
    assert "定时发布" in labels
    assert "发布" in labels


def test_submit_button_labels_default() -> None:
    assert _submit_button_labels({}) == ("发布",)


@pytest.mark.parametrize(
    ("submit_text", "metadata_has_schedule", "expected_first"),
    [
        ("发布", False, "发布"),
        ("发布", True, "定时发布"),
        ("定时发布", False, "定时发布"),
        ("", False, "发布"),
        ("", True, "定时发布"),
    ],
)
def test_labels_for_submit_text(
    submit_text: str, metadata_has_schedule: bool, expected_first: str,
) -> None:
    labels = _labels_for_submit_text(
        submit_text, metadata_has_schedule=metadata_has_schedule,
    )
    assert labels[0] == expected_first


def test_is_scheduled_submit_mode() -> None:
    assert _is_scheduled_submit_mode(_SUBMIT_TEXT_SCHEDULED)
    assert not _is_scheduled_submit_mode(_SUBMIT_TEXT_IMMEDIATE)


def test_max_ready_btn_sec_scheduled_longer() -> None:
    assert _max_ready_btn_sec(_SUBMIT_TEXT_IMMEDIATE) == _MAX_READY_BTN_SEC
    assert _max_ready_btn_sec(_SUBMIT_TEXT_SCHEDULED) == _MAX_READY_BTN_SEC_SCHEDULED
    assert _MAX_READY_BTN_SEC_SCHEDULED > _MAX_READY_BTN_SEC


@pytest.mark.parametrize(
    ("poll_index", "picker_open", "host_locked", "expected"),
    [
        (0, False, False, True),
        (1, False, False, False),
        (4, False, False, True),
        (2, True, False, True),
        (2, False, True, True),
    ],
)
def test_should_full_unlock_on_poll(
    poll_index: int, picker_open: bool, host_locked: bool, expected: bool,
) -> None:
    assert (
        _should_full_unlock_on_poll(
            poll_index, picker_open=picker_open, host_locked=host_locked,
        )
        is expected
    )


def test_format_submit_timeout_message_includes_host_state() -> None:
    msg = _format_submit_timeout_message(
        _SUBMIT_TEXT_SCHEDULED,
        {
            "submit_disabled": True,
            "schedule_picker_open": True,
            "submit_text": "定时发布",
            "sr_red_ready": False,
            "has_sr": True,
            "focus_in_schedule": True,
        },
        max_sec=120,
    )
    assert "120 秒" in msg
    assert "submit-disabled=True" in msg
    assert "浮层=开" in msg
    assert "_sr=有" in msg
    assert "红钮就绪=否" in msg
    assert "焦点仍在定时区" in msg
