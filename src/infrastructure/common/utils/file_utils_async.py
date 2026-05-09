"""
异步文件工具模块
文件路径：src/core/common/utils/file_utils_async.py
功能：提供异步文件读写、检查等工具函数
"""

import aiofiles
import os
from typing import Any, Optional, List
from pathlib import Path
import logging
import asyncio

logger = logging.getLogger(__name__)

async def read_file_async(file_path: str, mode: str = 'r', encoding: str = 'utf-8') -> Any:
    """异步读取文件
    
    Args:
        file_path: 文件路径
        mode: 读取模式
        encoding: 编码
        
    Returns:
        文件内容
    """
    try:
        async with aiofiles.open(file_path, mode, encoding=encoding if 'b' not in mode else None) as f:
            return await f.read()
    except Exception as e:
        logger.error(f"读取文件失败 {file_path}: {e}")
        raise

async def write_file_async(file_path: str, content: Any, mode: str = 'w', encoding: str = 'utf-8') -> None:
    """异步写入文件
    
    Args:
        file_path: 文件路径
        content: 内容
        mode: 写入模式
        encoding: 编码
    """
    try:
        # 确保目录存在
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        async with aiofiles.open(file_path, mode, encoding=encoding if 'b' not in mode else None) as f:
            await f.write(content)
    except Exception as e:
        logger.error(f"写入文件失败 {file_path}: {e}")
        raise

async def file_exists_async(file_path: str) -> bool:
    """异步检查文件是否存在 (实质上是包装了同步调用，因为os.path.exists很快)
    
    Args:
        file_path: 文件路径
        
    Returns:
        是否存在
    """
    return await asyncio.to_thread(os.path.exists, file_path)

async def delete_file_async(file_path: str) -> bool:
    """异步删除文件
    
    Args:
        file_path: 文件路径
        
    Returns:
        是否成功
    """
    try:
        if await file_exists_async(file_path):
            await asyncio.to_thread(os.remove, file_path)
            return True
        return False
    except Exception as e:
        logger.error(f"删除文件失败 {file_path}: {e}")
        return False
