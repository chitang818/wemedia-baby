"""
单发布页面工具函数单元测试（路径分割、图文判断等；话题解析见 test_work_description_topics）。
"""

from __future__ import annotations

import pytest

from src.ui.pages.publish.single_task_creation_page import (
    _split_comma_paths,
    _record_looks_like_image,
)

pytestmark = pytest.mark.unit


class TestSplitCommaPaths:

    def test_single_path(self):
        assert _split_comma_paths("/video.mp4") == ["/video.mp4"]

    def test_multiple_paths(self):
        result = _split_comma_paths("/a.jpg,/b.jpg,/c.jpg")
        assert result == ["/a.jpg", "/b.jpg", "/c.jpg"]

    def test_strips_whitespace(self):
        result = _split_comma_paths(" /a.jpg , /b.jpg ")
        assert result == ["/a.jpg", "/b.jpg"]

    def test_empty_string_returns_empty(self):
        assert _split_comma_paths("") == []

    def test_trailing_comma_ignored(self):
        result = _split_comma_paths("/a.jpg,")
        assert result == ["/a.jpg"]


class TestRecordLooksLikeImage:

    def test_file_type_image(self):
        assert _record_looks_like_image({"file_type": "image", "file_path": ""}) is True

    def test_file_type_video(self):
        assert _record_looks_like_image({"file_type": "video", "file_path": ""}) is False

    def test_infer_from_jpg_extension(self):
        assert _record_looks_like_image({"file_type": "", "file_path": "/img.jpg"}) is True

    def test_infer_from_png_extension(self):
        assert _record_looks_like_image({"file_type": "", "file_path": "/img.png"}) is True

    def test_infer_from_webp_extension(self):
        assert _record_looks_like_image({"file_type": "", "file_path": "/img.webp"}) is True

    def test_infer_from_mp4_extension(self):
        assert _record_looks_like_image({"file_type": "", "file_path": "/video.mp4"}) is False

    def test_multiple_images_in_path(self):
        assert _record_looks_like_image(
            {"file_type": "", "file_path": "/a.jpg,/b.png"}
        ) is True

    def test_empty_record(self):
        result = _record_looks_like_image({})
        assert isinstance(result, bool)
