"""
异步文件存储模块
文件路径：src/core/infrastructure/storage/file_storage.py
功能：提供异步文件操作，使用aiofiles替代同步文件操作
"""

import aiofiles
import json
from typing import Optional, Any, Dict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class AsyncFileStorage:
    """异步文件存储服务
    
    使用aiofiles进行所有文件操作，完全异步化。
    """
    
    def __init__(self, base_path: str = "data"):
        """初始化异步文件存储服务
        
        Args:
            base_path: 基础路径
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
    
    async def read_file(self, file_path: str, mode: str = "r", encoding: str = "utf-8") -> Any:
        """读取文件（异步）
        
        Args:
            file_path: 文件路径（相对或绝对）
            mode: 读取模式（'r'文本，'rb'二进制）
            encoding: 编码方式（仅文本模式有效）
        
        Returns:
            文件内容
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = (self.base_path / path).resolve()
        else:
            path = path.resolve()
        if not str(path).startswith(str(self.base_path.resolve())):
            raise ValueError(f"路径越界: {file_path}")
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if "b" in mode:
            encoding = None
            
        async with aiofiles.open(path, mode, encoding=encoding) as f:
            return await f.read()
    
    async def write_file(self, file_path: str, content: Any, mode: str = "w", encoding: str = "utf-8") -> None:
        """写入文件（异步）
        
        Args:
            file_path: 文件路径（相对或绝对）
            content: 文件内容
            mode: 写入模式（'w'文本，'wb'二进制）
            encoding: 编码方式（仅文本模式有效）
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = self.base_path / path
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if "b" in mode:
            encoding = None
            
        async with aiofiles.open(path, mode, encoding=encoding) as f:
            await f.write(content)
    
    async def read_cookie(self, cookie_path: str) -> Optional[Dict[str, Any]]:
        """读取Cookie文件（异步，JSON 格式）
        
        Args:
            cookie_path: Cookie文件路径
        
        Returns:
            Cookie字典，如果文件不存在返回None
        """
        try:
            content = await self.read_file(cookie_path, "r")
            return json.loads(content)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            # 兼容旧的 pickle 格式：尝试以二进制读取后 JSON 解析失败则返回 None
            self.logger.warning(f"Cookie 文件非 JSON 格式（可能是旧格式）: {cookie_path}")
            return None
        except Exception as e:
            self.logger.error(f"读取Cookie文件失败: {cookie_path}, 错误: {e}", exc_info=True)
            return None
    
    async def write_cookie(self, cookie_path: str, cookie_data: Dict[str, Any]) -> None:
        """写入Cookie文件（异步，JSON 格式）
        
        Args:
            cookie_path: Cookie文件路径
            cookie_data: Cookie数据字典
        """
        try:
            content = json.dumps(cookie_data, ensure_ascii=False, indent=2)
            await self.write_file(cookie_path, content, "w")
            self.logger.debug(f"写入Cookie文件成功: {cookie_path}")
        except Exception as e:
            self.logger.error(f"写入Cookie文件失败: {cookie_path}, 错误: {e}", exc_info=True)
            raise
    
    async def delete_file(self, file_path: str) -> bool:
        """删除文件（异步）
        
        Args:
            file_path: 文件路径
        
        Returns:
            如果删除成功返回True，否则返回False
        """
        try:
            path = Path(file_path)
            if not path.is_absolute():
                path = self.base_path / path
            
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception as e:
            self.logger.error(f"删除文件失败: {file_path}, 错误: {e}", exc_info=True)
            return False
    
    async def file_exists(self, file_path: str) -> bool:
        """检查文件是否存在（异步）
        
        Args:
            file_path: 文件路径
        
        Returns:
            如果文件存在返回True，否则返回False
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = self.base_path / path
        
        return path.exists()
    
    async def ensure_directory(self, dir_path: str) -> None:
        """确保目录存在（异步）
        
        Args:
            dir_path: 目录路径
        """
        path = Path(dir_path)
        if not path.is_absolute():
            path = self.base_path / path
        
        path.mkdir(parents=True, exist_ok=True)

