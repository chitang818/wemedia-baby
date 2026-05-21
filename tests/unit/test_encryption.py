"""
加密模块单元测试
测试 hash_password / verify_password 及 EncryptionManager 的加解密功能。
"""

import pytest
from unittest.mock import patch
from cryptography.fernet import Fernet

from src.infrastructure.common.security.encryption import (
    hash_password,
    verify_password,
    EncryptionManager,
)

pytestmark = pytest.mark.unit


class TestPasswordHashing:

    def test_hash_returns_string(self):
        result = hash_password("mypassword")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_is_not_plaintext(self):
        pw = "secret123"
        assert hash_password(pw) != pw

    def test_two_hashes_differ(self):
        """bcrypt 每次生成不同 salt，同一密码两次 hash 结果不同"""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2

    def test_verify_correct_password(self):
        pw = "correct_password"
        h = hash_password(pw)
        assert verify_password(pw, h) is True

    def test_verify_wrong_password(self):
        h = hash_password("correct")
        assert verify_password("wrong", h) is False

    def test_verify_empty_password(self):
        h = hash_password("something")
        assert verify_password("", h) is False

    def test_verify_invalid_hash_returns_false(self):
        """传入非 bcrypt 格式的 hash 应返回 False 而不抛异常"""
        assert verify_password("any", "not_a_valid_hash") is False


class TestEncryptionManager:

    def _get_fresh_key(self) -> bytes:
        return Fernet.generate_key()

    def test_encrypt_decrypt_roundtrip(self):
        key = self._get_fresh_key()
        with patch.object(EncryptionManager, "get_encryption_key", return_value=key):
            data = b"hello world"
            encrypted = EncryptionManager.encrypt_data(data)
            decrypted = EncryptionManager.decrypt_data(encrypted)
            assert decrypted == data

    def test_encrypt_cookie_roundtrip(self):
        key = self._get_fresh_key()
        with patch.object(EncryptionManager, "get_encryption_key", return_value=key):
            cookies = {"sessionid": "abc123", "token": "xyz"}
            encrypted = EncryptionManager.encrypt_cookie(cookies)
            decrypted = EncryptionManager.decrypt_cookie(encrypted)
            assert decrypted == cookies

    def test_encrypted_data_is_bytes(self):
        key = self._get_fresh_key()
        with patch.object(EncryptionManager, "get_encryption_key", return_value=key):
            result = EncryptionManager.encrypt_data(b"test")
            assert isinstance(result, bytes)

    def test_different_encryptions_differ(self):
        """同一明文每次加密结果应不同（Fernet 使用随机 IV）"""
        key = self._get_fresh_key()
        with patch.object(EncryptionManager, "get_encryption_key", return_value=key):
            e1 = EncryptionManager.encrypt_data(b"same data")
            e2 = EncryptionManager.encrypt_data(b"same data")
            assert e1 != e2

    def test_get_encryption_key_raises_on_keyring_failure(self):
        """keyring 不可用时应显式失败，避免生成重启后无法解密的临时密钥。"""
        with patch("keyring.get_password", side_effect=Exception("keyring unavailable")):
            with pytest.raises(RuntimeError, match="系统密钥链不可用"):
                EncryptionManager.get_encryption_key("test_key")
