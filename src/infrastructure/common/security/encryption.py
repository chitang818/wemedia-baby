"""
加密模块（优化版）
文件路径：src/core/common/security/encryption.py
功能：提供密码哈希和Cookie加密功能，使用keyring管理密钥
"""

import bcrypt
from cryptography.fernet import Fernet
from typing import Optional
import logging
import keyring

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """使用bcrypt哈希密码
    
    Args:
        password: 明文密码
    
    Returns:
        密码哈希字符串
    """
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
    return password_hash.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码
    
    Args:
        password: 明文密码
        password_hash: 密码哈希字符串
    
    Returns:
        如果密码匹配返回True，否则返回False
    """
    try:
        return bcrypt.checkpw(
            password.encode('utf-8'),
            password_hash.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"密码验证失败: {e}")
        return False


class EncryptionManager:
    """加密管理器 - 使用keyring管理密钥"""
    
    SERVICE_NAME = "媒小宝"
    
    @staticmethod
    def get_encryption_key(key_name: str = "encryption_key") -> bytes:
        """从keyring获取加密密钥
        
        Args:
            key_name: 密钥名称
        
        Returns:
            加密密钥（bytes），如果不存在则生成并保存
        """
        try:
            key_str = keyring.get_password(EncryptionManager.SERVICE_NAME, key_name)
            if key_str:
                return key_str.encode()
            else:
                # 生成新密钥
                key = Fernet.generate_key()
                keyring.set_password(
                    EncryptionManager.SERVICE_NAME,
                    key_name,
                    key.decode()
                )
                logger.info(f"生成并保存加密密钥: {key_name}")
                return key
        except Exception as e:
            logger.error("keyring 不可用，无法持久化加密密钥: %s", e)
            raise RuntimeError(
                "系统密钥链不可用，无法安全保存或读取加密密钥。"
            ) from e
    
    @staticmethod
    def encrypt_data(data: bytes, key_name: str = "encryption_key") -> bytes:
        """加密数据
        
        Args:
            data: 要加密的数据（bytes）
            key_name: 密钥名称
        
        Returns:
            加密后的数据（bytes）
        """
        key = EncryptionManager.get_encryption_key(key_name)
        fernet = Fernet(key)
        return fernet.encrypt(data)
    
    @staticmethod
    def decrypt_data(encrypted_data: bytes, key_name: str = "encryption_key") -> bytes:
        """解密数据
        
        Args:
            encrypted_data: 加密的数据（bytes）
            key_name: 密钥名称
        
        Returns:
            解密后的数据（bytes）
        """
        key = EncryptionManager.get_encryption_key(key_name)
        fernet = Fernet(key)
        return fernet.decrypt(encrypted_data)
    
    @staticmethod
    def encrypt_cookie(cookie_data: dict, key_name: str = "encryption_key") -> bytes:
        """加密Cookie数据
        
        Args:
            cookie_data: Cookie数据字典
            key_name: 密钥名称
        
        Returns:
            加密后的Cookie数据（bytes）
        """
        import json
        data = json.dumps(cookie_data, ensure_ascii=False).encode('utf-8')
        return EncryptionManager.encrypt_data(data, key_name)
    
    @staticmethod
    def decrypt_cookie(encrypted_cookie: bytes, key_name: str = "encryption_key") -> dict:
        """解密Cookie数据
        
        Args:
            encrypted_cookie: 加密的Cookie数据（bytes）
            key_name: 密钥名称
        
        Returns:
            Cookie数据字典
        """
        import json
        data = EncryptionManager.decrypt_data(encrypted_cookie, key_name)
        return json.loads(data.decode('utf-8'))

