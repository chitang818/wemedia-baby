"""
数据脱敏工具函数测试
"""
import pytest
from src.utils.masking import mask_username, mask_ip, mask_token, mask_cookie_domain


class TestMaskUsername:
    def test_empty(self):
        assert mask_username("") == ""

    def test_single_char(self):
        assert mask_username("A") == "A*"

    def test_two_chars(self):
        assert mask_username("AB") == "A*"

    def test_normal(self):
        assert mask_username("zhang") == "z***g"

    def test_chinese(self):
        assert mask_username("张三丰") == "张*丰"


class TestMaskIp:
    def test_empty(self):
        assert mask_ip("") == ""

    def test_ipv4(self):
        assert mask_ip("192.168.1.100") == "192.168.*.*"

    def test_short(self):
        assert mask_ip("::1") == "::1"


class TestMaskToken:
    def test_empty(self):
        assert mask_token("") == ""

    def test_short(self):
        assert mask_token("abcd") == "ab***"

    def test_normal(self):
        result = mask_token("abcdefghij1234567890")
        assert result.startswith("abc")
        assert result.endswith("890")
        assert "..." in result


class TestMaskCookieDomain:
    def test_empty(self):
        assert mask_cookie_domain(None) == "<empty>"

    def test_list(self):
        cookies = [{"domain": ".douyin.com"}, {"domain": ".douyin.com"}]
        result = mask_cookie_domain(cookies)
        assert "2 cookies" in result
        assert ".douyin.com" in result

    def test_dict(self):
        result = mask_cookie_domain({"domain": ".example.com"})
        assert ".example.com" in result
