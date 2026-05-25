from __future__ import annotations

import pytest

from src.plugins.pro.xiaohongshu.steps.step_08_submit import (
    _is_xhs_publish_edit_url,
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
            "https://creator.xiaohongshu.com/new/note/manage",
            False,
        ),
        (
            "https://creator.xiaohongshu.com/publish/success",
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
        ("https://creator.xiaohongshu.com/publish/success", True),
        (
            "https://creator.xiaohongshu.com/publish/publish?target=video",
            False,
        ),
        ("https://example.com/", False),
    ],
)
def test_url_indicates_success(url: str, expected: bool) -> None:
    assert _url_indicates_success(url) is expected
