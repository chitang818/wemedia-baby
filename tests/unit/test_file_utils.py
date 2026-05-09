"""
文件工具函数单元测试
模块：src/utils/file_utils.py
"""
import os
import pytest
from pathlib import Path
from src.utils.file_utils import (
    get_file_size,
    get_file_extension,
    ensure_directory_exists,
    is_valid_video_file,
    is_valid_image_file,
    is_valid_media_file,
    get_file_name,
    get_file_name_with_extension,
    format_file_size,
)


class TestGetFileExtension:
    def test_mp4(self):
        assert get_file_extension("video.mp4") == "mp4"

    def test_uppercase(self):
        assert get_file_extension("video.MP4") == "mp4"

    def test_no_extension(self):
        assert get_file_extension("no_ext") == ""

    def test_nested_path(self):
        assert get_file_extension("/path/to/file.jpg") == "jpg"


class TestGetFileName:
    def test_stem_only(self):
        assert get_file_name("/path/to/video.mp4") == "video"

    def test_no_extension(self):
        assert get_file_name("somefile") == "somefile"


class TestGetFileNameWithExtension:
    def test_basename(self):
        assert get_file_name_with_extension("/path/to/video.mp4") == "video.mp4"


class TestFormatFileSize:
    def test_bytes(self):
        assert format_file_size(512) == "512 B"

    def test_kilobytes(self):
        result = format_file_size(2048)
        assert "KB" in result

    def test_megabytes(self):
        result = format_file_size(5 * 1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self):
        result = format_file_size(2 * 1024 * 1024 * 1024)
        assert "GB" in result


class TestGetFileSize:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        size = get_file_size(str(f))
        assert size == 5

    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            get_file_size("/nonexistent/path/file.txt")


class TestEnsureDirectoryExists:
    def test_creates_new_dir(self, tmp_path):
        new_dir = str(tmp_path / "subdir" / "nested")
        ensure_directory_exists(new_dir)
        assert os.path.isdir(new_dir)

    def test_existing_dir_no_error(self, tmp_path):
        ensure_directory_exists(str(tmp_path))


class TestIsValidVideoFile:
    def test_valid_extension_and_exists(self, tmp_path):
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"\x00")
        assert is_valid_video_file(str(f)) is True

    def test_invalid_extension(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"\x00")
        assert is_valid_video_file(str(f)) is False

    def test_nonexistent_file(self):
        assert is_valid_video_file("/no/such/file.mp4") is False


class TestIsValidImageFile:
    def test_valid_jpg(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\x00")
        assert is_valid_image_file(str(f)) is True

    def test_invalid_extension(self, tmp_path):
        f = tmp_path / "photo.bmp2"
        f.write_bytes(b"\x00")
        assert is_valid_image_file(str(f)) is False

    def test_nonexistent_file(self):
        assert is_valid_image_file("/no/such/file.jpg") is False


class TestIsValidMediaFile:
    def test_video_is_valid(self, tmp_path):
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"\x00")
        assert is_valid_media_file(str(f)) is True

    def test_image_is_valid(self, tmp_path):
        f = tmp_path / "photo.png"
        f.write_bytes(b"\x00")
        assert is_valid_media_file(str(f)) is True

    def test_invalid_type(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"\x00")
        assert is_valid_media_file(str(f)) is False
