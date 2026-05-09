"""
缓存管理器
文件路径：src/core/cache/cache_manager.py
功能：提供通用的缓存管理功能
"""

import time
from typing import Dict, Any, Optional, Callable
from collections import OrderedDict
import logging
import threading

logger = logging.getLogger(__name__)


class CacheEntry:
    """缓存条目"""
    
    def __init__(self, key: str, value: Any, ttl: int = 3600):
        """初始化缓存条目
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 生存时间（秒）
        """
        self.key = key
        self.value = value
        self.ttl = ttl
        self.created_at = time.time()
        self.access_count = 0
        self.last_accessed = time.time()
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() - self.created_at > self.ttl
    
    def touch(self):
        """更新访问时间"""
        self.access_count += 1
        self.last_accessed = time.time()
    
    def get_age(self) -> float:
        """获取缓存条目年龄（秒）"""
        return time.time() - self.created_at


class CacheManager:
    """缓存管理器 - 提供通用的缓存功能"""
    
    def __init__(
        self,
        max_size: int = 100,
        default_ttl: int = 3600,
        cleanup_interval: int = 3600
    ):
        """初始化缓存管理器
        
        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认生存时间（秒）
            cleanup_interval: 清理间隔（秒）
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cleanup_interval = cleanup_interval
        
        # 使用 OrderedDict 实现 LRU 缓存
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        
        # 统计信息
        self._hits = 0
        self._misses = 0
        
        logger.info(
            f"缓存管理器初始化: max_size={max_size}, "
            f"default_ttl={default_ttl}s, cleanup_interval={cleanup_interval}s"
        )
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值
        
        Args:
            key: 缓存键
            default: 默认值（如果不存在）
            
        Returns:
            缓存值，不存在或已过期返回默认值
        """
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._misses += 1
                return default
            
            if entry.is_expired():
                # 已过期，删除
                del self._cache[key]
                self._misses += 1
                return default
            
            # 更新访问时间（LRU）
            entry.touch()
            self._cache.move_to_end(key)
            self._hits += 1
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 生存时间（秒），None 使用默认值
        """
        with self._lock:
            # 如果已存在，先删除
            if key in self._cache:
                del self._cache[key]
            
            # 检查是否超过最大大小
            if len(self._cache) >= self.max_size:
                # 删除最旧的条目（LRU）
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                logger.debug(f"缓存已满，删除最旧条目: {oldest_key}")
            
            # 添加新条目
            entry = CacheEntry(key, value, ttl or self.default_ttl)
            self._cache[key] = entry
            self._cache.move_to_end(key)
    
    def delete(self, key: str) -> bool:
        """删除缓存条目
        
        Args:
            key: 缓存键
            
        Returns:
            是否成功删除
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self):
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            logger.info("缓存已清空")
    
    def cleanup_expired(self) -> int:
        """清理过期条目
        
        Returns:
            清理的条目数
        """
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                logger.debug(f"清理过期缓存条目: {len(expired_keys)} 个")
            
            return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.2f}%",
                "total_requests": total_requests
            }
    
    def exists(self, key: str) -> bool:
        """检查缓存键是否存在且未过期
        
        Args:
            key: 缓存键
            
        Returns:
            是否存在且未过期
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._cache[key]
                return False
            return True
    
    def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: Optional[int] = None
    ) -> Any:
        """获取缓存值，如果不存在则调用工厂函数生成并缓存
        
        Args:
            key: 缓存键
            factory: 工厂函数（无参数，返回要缓存的值）
            ttl: 生存时间（秒）
            
        Returns:
            缓存值
        """
        value = self.get(key)
        if value is None:
            value = factory()
            self.set(key, value, ttl)
        return value

