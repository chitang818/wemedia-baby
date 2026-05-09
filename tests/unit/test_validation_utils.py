"""
验证工具函数单元测试
模块：src/utils/validation_utils.py
"""
import pytest
from src.utils.validation_utils import (
    validate_username,
    validate_email,
    validate_password,
    validate_platform,
    validate_file_type,
    validate_account_name,
    validate_url,
)


class TestValidateUsername:
    def test_valid_username(self):
        assert validate_username("user123") is True

    def test_valid_username_with_underscore(self):
        assert validate_username("my_user") is True

    def test_min_length(self):
        assert validate_username("abc") is True

    def test_too_short(self):
        assert validate_username("ab") is False

    def test_too_long(self):
        assert validate_username("a" * 21) is False

    def test_max_length(self):
        assert validate_username("a" * 20) is True

    def test_empty_string(self):
        assert validate_username("") is False

    def test_none(self):
        assert validate_username(None) is False  # type: ignore

    def test_special_chars_rejected(self):
        assert validate_username("user@123") is False

    def test_chinese_rejected(self):
        assert validate_username("用户名") is False


class TestValidateEmail:
    def test_valid_email(self):
        assert validate_email("user@example.com") is True

    def test_valid_email_with_subdomain(self):
        assert validate_email("user@mail.example.com") is True

    def test_no_at_sign(self):
        assert validate_email("userexample.com") is False

    def test_no_domain(self):
        assert validate_email("user@") is False

    def test_empty_string(self):
        assert validate_email("") is False

    def test_none(self):
        assert validate_email(None) is False  # type: ignore


class TestValidatePassword:
    def test_valid_password(self):
        assert validate_password("password1") is True

    def test_too_short(self):
        assert validate_password("pass1") is False

    def test_only_letters(self):
        assert validate_password("password") is False

    def test_only_numbers(self):
        assert validate_password("12345678") is False

    def test_empty_string(self):
        assert validate_password("") is False

    def test_none(self):
        assert validate_password(None) is False  # type: ignore

    def test_letters_and_digits(self):
        assert validate_password("abcdef12") is True


class TestValidatePlatform:
    def test_douyin_valid(self):
        assert validate_platform("douyin") is True

    def test_kuaishou_valid(self):
        assert validate_platform("kuaishou") is True

    def test_xiaohongshu_valid(self):
        assert validate_platform("xiaohongshu") is True

    def test_unknown_platform(self):
        assert validate_platform("weibo") is False

    def test_empty_string(self):
        assert validate_platform("") is False

    def test_none(self):
        assert validate_platform(None) is False  # type: ignore

    def test_uppercase_treated_as_valid(self):
        # validate_platform 调用 .lower()
        assert validate_platform("DOUYIN") is True


class TestValidateFileType:
    def test_mp4_allowed(self):
        assert validate_file_type("video.mp4", ["mp4", "mov"]) is True

    def test_extension_case_insensitive(self):
        assert validate_file_type("video.MP4", ["mp4"]) is True

    def test_not_in_allowed_list(self):
        assert validate_file_type("video.avi", ["mp4", "mov"]) is False

    def test_empty_file_path(self):
        assert validate_file_type("", ["mp4"]) is False

    def test_empty_allowed_types(self):
        assert validate_file_type("video.mp4", []) is False


class TestValidateAccountName:
    def test_valid_name(self):
        assert validate_account_name("抖音账号1") is True

    def test_single_char(self):
        assert validate_account_name("A") is True

    def test_empty_string(self):
        assert validate_account_name("") is False

    def test_none(self):
        assert validate_account_name(None) is False  # type: ignore

    def test_50_chars(self):
        assert validate_account_name("a" * 50) is True

    def test_51_chars(self):
        assert validate_account_name("a" * 51) is False


class TestValidateUrl:
    def test_http_url(self):
        assert validate_url("http://example.com") is True

    def test_https_url(self):
        assert validate_url("https://example.com/path?q=1") is True

    def test_no_scheme(self):
        assert validate_url("example.com") is False

    def test_empty_string(self):
        assert validate_url("") is False

    def test_none(self):
        assert validate_url(None) is False  # type: ignore

    def test_localhost(self):
        assert validate_url("http://localhost:8080") is True
