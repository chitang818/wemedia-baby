"""
媒体文件验证器单元测试
模块：src/services/common/media_validator.py
"""
import pytest
from pathlib import Path
from src.services.common.media_validator import (
    MediaValidator,
    SUPPORTED_VIDEO_FORMATS,
    SUPPORTED_IMAGE_FORMATS,
    PLATFORM_SIZE_LIMITS,
)


@pytest.fixture
def validator():
    return MediaValidator()


class TestValidateFormat:
    def test_valid_video_mp4(self, validator, tmp_path):
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"\x00")
        assert validator.validate_format(str(f), "video", "douyin") is True

    def test_valid_image_jpg(self, validator, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\x00")
        assert validator.validate_format(str(f), "image", "douyin") is True

    def test_invalid_video_extension(self, validator):
        assert validator.validate_format("file.docx", "video", "douyin") is False

    def test_invalid_image_extension(self, validator):
        assert validator.validate_format("file.mp4", "image", "douyin") is False

    def test_unknown_file_type(self, validator):
        assert validator.validate_format("file.mp4", "audio", "douyin") is False

    def test_nonexistent_video_file(self, validator):
        assert validator.validate_format("/no/such/file.mp4", "video", "douyin") is False


class TestValidateSize:
    def test_small_video_passes(self, validator, tmp_path):
        f = tmp_path / "small.mp4"
        f.write_bytes(b"\x00" * 1024)
        assert validator.validate_size(str(f), "video", "douyin") is True

    def test_file_not_found_returns_false(self, validator):
        assert validator.validate_size("/no/such/file.mp4", "video", "douyin") is False

    def test_unknown_platform_uses_default_limit(self, validator, tmp_path):
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"\x00" * 100)
        assert validator.validate_size(str(f), "video", "unknown_platform") is True


class TestValidateCombined:
    def test_valid_file(self, validator, tmp_path):
        f = tmp_path / "good.mp4"
        f.write_bytes(b"\x00" * 100)
        ok, msg = validator.validate(str(f), "video", "douyin")
        assert ok is True
        assert msg == ""

    def test_nonexistent_file(self, validator):
        ok, msg = validator.validate("/no/such/file.mp4", "video", "douyin")
        assert ok is False
        assert "不存在" in msg

    def test_wrong_extension(self, validator, tmp_path):
        f = tmp_path / "bad.exe"
        f.write_bytes(b"\x00")
        ok, msg = validator.validate(str(f), "video", "douyin")
        assert ok is False


class TestPlatformSizeLimits:
    def test_douyin_video_limit_is_4gb(self):
        limit = PLATFORM_SIZE_LIMITS["douyin"]["video"]
        assert limit == 4 * 1024 * 1024 * 1024

    def test_kuaishou_video_limit_is_2gb(self):
        limit = PLATFORM_SIZE_LIMITS["kuaishou"]["video"]
        assert limit == 2 * 1024 * 1024 * 1024

    def test_supported_formats_not_empty(self):
        assert len(SUPPORTED_VIDEO_FORMATS) > 0
        assert len(SUPPORTED_IMAGE_FORMATS) > 0
