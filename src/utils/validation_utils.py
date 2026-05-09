"""
验证工具模块
文件路径：src/utils/validation_utils.py
功能：提供数据验证相关的工具函数
"""

import re
from typing import Optional


# 支持的平台列表
SUPPORTED_PLATFORMS = {'douyin', 'kuaishou', 'xiaohongshu'}

# 用户名规则：3-20个字符，只能包含字母、数字、下划线
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]{3,20}$')

# 邮箱正则表达式
EMAIL_PATTERN = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)

# 密码规则：至少8个字符，包含字母和数字
PASSWORD_PATTERN = re.compile(r'^(?=.*[a-zA-Z])(?=.*\d).{8,}$')


def validate_username(username: str) -> bool:
    """验证用户名格式
    
    规则：
    - 长度：3-20个字符
    - 只能包含字母、数字、下划线
    
    Args:
        username: 用户名
    
    Returns:
        如果格式正确返回True，否则返回False
    """
    if not username or not isinstance(username, str):
        return False
    
    return bool(USERNAME_PATTERN.match(username.strip()))


def validate_email(email: str) -> bool:
    """验证邮箱格式
    
    Args:
        email: 邮箱地址
    
    Returns:
        如果格式正确返回True，否则返回False
    """
    if not email or not isinstance(email, str):
        return False
    
    return bool(EMAIL_PATTERN.match(email.strip()))


def validate_password(password: str) -> bool:
    """验证密码强度
    
    规则：
    - 至少8个字符
    - 必须包含字母和数字
    
    Args:
        password: 密码
    
    Returns:
        如果密码强度符合要求返回True，否则返回False
    """
    if not password or not isinstance(password, str):
        return False
    
    return bool(PASSWORD_PATTERN.match(password))


def validate_platform(platform: str) -> bool:
    """验证平台名称
    
    Args:
        platform: 平台名称（douyin/kuaishou/xiaohongshu）
    
    Returns:
        如果是支持的平台返回True，否则返回False
    """
    if not platform or not isinstance(platform, str):
        return False
    
    return platform.lower() in SUPPORTED_PLATFORMS


def validate_file_type(file_path: str, allowed_types: list) -> bool:
    """验证文件类型
    
    Args:
        file_path: 文件路径
        allowed_types: 允许的文件类型列表（扩展名，不含点号），如 ['mp4', 'mov']
    
    Returns:
        如果文件类型在允许列表中返回True，否则返回False
    """
    if not file_path or not allowed_types:
        return False
    
    from .file_utils import get_file_extension
    extension = get_file_extension(file_path)
    return extension.lower() in [t.lower() for t in allowed_types]


def validate_file_size(file_path: str, max_size: int) -> bool:
    """验证文件大小
    
    Args:
        file_path: 文件路径
        max_size: 最大文件大小（字节）
    
    Returns:
        如果文件大小不超过限制返回True，否则返回False
    """
    if not file_path:
        return False
    
    try:
        from .file_utils import get_file_size
        file_size = get_file_size(file_path)
        return file_size <= max_size
    except (FileNotFoundError, OSError):
        return False


def validate_account_name(account_name: str) -> bool:
    """验证账号名称
    
    规则：
    - 长度：1-50个字符
    - 不能为空
    
    Args:
        account_name: 账号名称
    
    Returns:
        如果格式正确返回True，否则返回False
    """
    if not account_name or not isinstance(account_name, str):
        return False
    
    name = account_name.strip()
    return 1 <= len(name) <= 50


def validate_url(url: str) -> bool:
    """验证URL格式
    
    Args:
        url: URL字符串
    
    Returns:
        如果URL格式正确返回True，否则返回False
    """
    if not url or not isinstance(url, str):
        return False
    
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    
    return bool(url_pattern.match(url.strip()))

