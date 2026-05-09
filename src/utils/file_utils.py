"""
文件操作工具模块
文件路径：src/utils/file_utils.py
功能：提供文件操作相关的工具函数
"""

import os
from typing import Optional
from pathlib import Path


def get_file_size(file_path: str) -> int:
    """获取文件大小（字节）
    
    Args:
        file_path: 文件路径
    
    Returns:
        文件大小（字节）
    
    Raises:
        FileNotFoundError: 文件不存在
        OSError: 文件访问错误
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    try:
        return os.path.getsize(file_path)
    except OSError as e:
        raise OSError(f"获取文件大小失败: {e}")


def get_file_extension(file_path: str) -> str:
    """获取文件扩展名（不含点号）
    
    Args:
        file_path: 文件路径
    
    Returns:
        文件扩展名（小写，不含点号），如 "mp4", "jpg"
    """
    return Path(file_path).suffix.lstrip('.').lower()


def ensure_directory_exists(dir_path: str) -> None:
    """确保目录存在，如果不存在则创建
    
    Args:
        dir_path: 目录路径
    
    Raises:
        OSError: 目录创建失败
    """
    try:
        os.makedirs(dir_path, exist_ok=True)
    except OSError as e:
        raise OSError(f"创建目录失败: {e}")


def is_valid_video_file(file_path: str) -> bool:
    """检查是否为有效的视频文件
    
    Args:
        file_path: 文件路径
    
    Returns:
        如果是有效的视频文件返回True，否则返回False
    """
    if not os.path.exists(file_path):
        return False
    
    valid_extensions = {'mp4', 'mov', 'avi', 'mkv', 'flv', 'wmv', 'webm'}
    extension = get_file_extension(file_path)
    return extension in valid_extensions


def is_valid_image_file(file_path: str) -> bool:
    """检查是否为有效的图片文件
    
    Args:
        file_path: 文件路径
    
    Returns:
        如果是有效的图片文件返回True，否则返回False
    """
    if not os.path.exists(file_path):
        return False
    
    valid_extensions = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'}
    extension = get_file_extension(file_path)
    return extension in valid_extensions


def is_valid_media_file(file_path: str) -> bool:
    """检查是否为有效的媒体文件（视频或图片）
    
    Args:
        file_path: 文件路径
    
    Returns:
        如果是有效的媒体文件返回True，否则返回False
    """
    return is_valid_video_file(file_path) or is_valid_image_file(file_path)


def get_file_name(file_path: str) -> str:
    """获取文件名（不含路径和扩展名）
    
    Args:
        file_path: 文件路径
    
    Returns:
        文件名（不含扩展名）
    """
    return Path(file_path).stem


def get_file_name_with_extension(file_path: str) -> str:
    """获取文件名（含扩展名）
    
    Args:
        file_path: 文件路径
    
    Returns:
        文件名（含扩展名）
    """
    return Path(file_path).name


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小
    
    Args:
        size_bytes: 文件大小（字节）
    
    Returns:
        格式化后的文件大小字符串，如 "1.5 MB"
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

