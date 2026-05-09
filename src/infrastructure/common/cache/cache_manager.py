"""
缓存管理器模块（优化版 - 二级缓存）
文件路径：src/core/common/cache/cache_manager.py
功能：提供二级缓存管理功能，支持L1内存缓存和L2文件缓存
"""

import json
import time
import asyncio
from typing import Dict, Any, Optional, List
from collections import OrderedDict
import logging
from pathlib import Path

try:
    import aiocache
    from aiocache import Cache
    AIOCACHE_AVAILABLE = True
except ImportError:
    AIOCACHE_AVAILABLE = False
    Cache = None

from src.infrastructure.storage.file_storage import AsyncFileStorage

logger = logging.getLogger(__name__)


class CacheManager:
    """二级缓存管理器
    
    提供L1内存缓存和L2文件缓存，支持缓存预热和一致性维护。
    """
    
    def __init__(
        self,
        l1_max_size: int = 100,
        l1_default_ttl: int = 3600,
        l2_cache_dir: str = "data/cache",
        l2_default_ttl: int = 86400  # 24小时
    ):
        """初始化二级缓存管理器
        
        Args:
            l1_max_size: L1内存缓存最大条目数
            l1_default_ttl: L1默认生存时间（秒）
            l2_cache_dir: L2文件缓存目录
            l2_default_ttl: L2默认生存时间（秒）
        """
        self.l1_max_size = l1_max_size
        self.l1_default_ttl = l1_default_ttl
        self.l2_cache_dir = Path(l2_cache_dir)
        self.l2_default_ttl = l2_default_ttl
        
        # L1内存缓存（使用OrderedDict实现LRU）
        self._l1_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._l1_lock = asyncio.Lock()
        
        # L2文件缓存
        self._file_storage = AsyncFileStorage(str(self.l2_cache_dir))
        
        # 统计信息
        self._l1_hits = 0
        self._l1_misses = 0
        self._l2_hits = 0
        self._l2_misses = 0
        
        # 确保L2缓存目录存在
        self.l2_cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(
            f"二级缓存管理器初始化: L1(max_size={l1_max_size}, ttl={l1_default_ttl}s), "
            f"L2(dir={l2_cache_dir}, ttl={l2_default_ttl}s)"
        )
    
    async def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值（异步）
        
        先查L1，再查L2，如果L2命中则加载到L1。
        
        Args:
            key: 缓存键
            default: 默认值（如果不存在）
        
        Returns:
            缓存值，不存在或已过期返回默认值
        """
        # 先查L1
        async with self._l1_lock:
            if key in self._l1_cache:
                entry = self._l1_cache[key]
                if time.time() - entry['created_at'] < entry['ttl']:
                    # L1命中
                    self._l1_hits += 1
                    entry['last_accessed'] = time.time()
                    # 移动到末尾（LRU）
                    self._l1_cache.move_to_end(key)
                    return entry['value']
                else:
                    # L1过期，删除
                    del self._l1_cache[key]
                    self._l1_misses += 1
        
        # L1未命中，查L2（优先 JSON，兼容旧 .pkl）
        l2_path_json = self.l2_cache_dir / f"{key}.json"
        l2_path_pkl = self.l2_cache_dir / f"{key}.pkl"
        l2_path = l2_path_json if l2_path_json.exists() else l2_path_pkl
        if await self._file_storage.file_exists(str(l2_path)):
            try:
                content = await self._file_storage.read_file(str(l2_path), "r")
                entry = json.loads(content)
                
                # 检查是否过期
                if time.time() - entry['created_at'] < entry['ttl']:
                    # L2命中，加载到L1
                    self._l2_hits += 1
                    async with self._l1_lock:
                        self._l1_cache[key] = entry
                        # 如果超过最大大小，删除最旧的
                        if len(self._l1_cache) > self.l1_max_size:
                            self._l1_cache.popitem(last=False)
                    
                    return entry['value']
                else:
                    # L2过期，删除
                    await self._file_storage.delete_file(str(l2_path))
                    self._l2_misses += 1
            except Exception as e:
                logger.error(f"读取L2缓存失败: {key}, 错误: {e}", exc_info=True)
                self._l2_misses += 1
        else:
            self._l2_misses += 1
        
        return default
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值（异步）
        
        同时更新L1和L2，确保一致性。
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 生存时间（秒），如果为None使用默认值
        """
        if ttl is None:
            ttl = self.l1_default_ttl
        
        now = time.time()
        entry = {
            'value': value,
            'created_at': now,
            'last_accessed': now,
            'ttl': ttl
        }
        
        # 更新L1
        async with self._l1_lock:
            self._l1_cache[key] = entry
            # 如果超过最大大小，删除最旧的
            if len(self._l1_cache) > self.l1_max_size:
                self._l1_cache.popitem(last=False)
        
        # 更新L2（使用 JSON 格式替代 pickle）
        try:
            l2_path = self.l2_cache_dir / f"{key}.json"
            content = json.dumps(entry, ensure_ascii=False)
            await self._file_storage.write_file(str(l2_path), content, "w")
        except Exception as e:
            logger.error(f"写入L2缓存失败: {key}, 错误: {e}", exc_info=True)
    
    async def invalidate(self, key: str) -> None:
        """失效缓存条目（异步）
        
        同时删除L1和L2中的条目。
        
        Args:
            key: 缓存键
        """
        # 删除L1
        async with self._l1_lock:
            if key in self._l1_cache:
                del self._l1_cache[key]
        
        # 删除L2
        l2_path = self.l2_cache_dir / f"{key}.pkl"
        await self._file_storage.delete_file(str(l2_path))
    
    async def clear(self) -> Dict[str, Any]:
        """清空所有应用缓存（异步）
        
        包括：
        1. L1 内存缓存
        2. L2 文件缓存 (.pkl)
        3. 运行日志文件
        4. 浏览器临时环境 (temp_ 开头的目录)
        
        Returns:
            清理统计信息
        """
        results = {
            "l1_cleared": 0,
            "l2_cleared": 0,
            "logs_cleared": 0,
            "browser_temp_cleared": 0
        }
        
        # 1. 清空L1
        async with self._l1_lock:
            results["l1_cleared"] = len(self._l1_cache)
            self._l1_cache.clear()
        
        # 2. 清空L2（pkl文件）
        results["l2_cleared"] = await self._clear_l2_cache()
        
        # 3. 清理日志
        results["logs_cleared"] = await self._clear_logs()
        
        # 4. 清理浏览器临时目录
        results["browser_temp_cleared"] = await self._clear_browser_temp()
        
        logger.info(f"深度清理完成: {results}")
        return results

    async def _clear_l2_cache(self) -> int:
        """清理L2 .pkl 缓存文件"""
        count = 0
        try:
            for cache_file in self.l2_cache_dir.glob("*.pkl"):
                await self._file_storage.delete_file(str(cache_file))
                count += 1
        except Exception as e:
            logger.error(f"清空L2缓存失败: {e}")
        return count

    async def _clear_logs(self) -> int:
        """清理日志文件"""
        count = 0
        try:
            from src.infrastructure.common.path_manager import PathManager
            
            # 1. 清理全局日志
            log_dir = PathManager.get_log_dir()
            if log_dir.exists():
                for log_file in log_dir.glob("*.log*"):
                    try:
                        os.remove(log_file)
                        count += 1
                    except Exception:
                        pass
            
            # 2. 清理账号日志: data/{platform}/{account}/workspace/logs
            app_data = PathManager.get_app_data_dir()
            data_dir = app_data / "data"
            
            if data_dir.exists():
                from src.utils.platform_names import PLATFORM_ID_TO_NAME
                # 遍历平台目录（仅处理已知平台，跳过 checkpoints/ 等系统目录）
                for platform_dir in data_dir.iterdir():
                    if platform_dir.is_dir() and platform_dir.name in PLATFORM_ID_TO_NAME:
                        # 遍历账号目录
                        for account_dir in platform_dir.iterdir():
                            if account_dir.is_dir():
                                logs_dir = account_dir / "workspace" / "logs"
                                if logs_dir.exists():
                                    for log_file in logs_dir.glob("*.log*"):
                                        try:
                                            os.remove(log_file)
                                            count += 1
                                        except Exception:
                                            pass
        except Exception as e:
            logger.error(f"清理日志失败: {e}")
        return count

    async def _clear_browser_temp(self) -> int:
        """清理浏览器缓存和临时工作目录"""
        count = 0
        try:
            import shutil
            from src.infrastructure.common.path_manager import PathManager
            
            app_data = PathManager.get_app_data_dir()
            data_dir = app_data / "data"
            
            if not data_dir.exists():
                return 0
                
            from src.utils.platform_names import PLATFORM_ID_TO_NAME
            # 遍历平台目录（仅处理已知平台，跳过 checkpoints/ 等系统目录）
            for platform_dir in data_dir.iterdir():
                if not platform_dir.is_dir() or platform_dir.name not in PLATFORM_ID_TO_NAME:
                    continue
                    
                # 遍历账号目录
                for account_dir in platform_dir.iterdir():
                    if not account_dir.is_dir():
                        continue
                        
                    # 1. 清理 QtWebEngine 缓存: qt_profile/cache, qt_profile/Code Cache, etc.
                    qt_profile = account_dir / "qt_profile"
                    targets = ["cache", "Code Cache", "GPUCache", "ShaderCache"]
                    for target in targets:
                        target_dir = qt_profile / target
                        if target_dir.exists():
                            try:
                                shutil.rmtree(target_dir)
                                count += 1
                            except Exception:
                                pass
                                
                    # 2. 清理工作区临时文件: workspace/temp
                    temp_dir = account_dir / "workspace" / "temp"
                    if temp_dir.exists():
                        try:
                            # 清空目录但不删除目录本身
                            for item in temp_dir.iterdir():
                                if item.is_file():
                                    os.remove(item)
                                elif item.is_dir():
                                    shutil.rmtree(item)
                            count += 1
                        except Exception:
                            pass
                            
                    # 3. (可选) 清理 Playwright 临时文件 (如果有 temp_ 开头)
                    browser_dir = account_dir / "browser"
                    if browser_dir.exists():
                        pass 
                        # Playwright 缓存较复杂，暂不清理 Default/Cache 避免影响会话，除非用户明确要求
                        
        except Exception as e:
            logger.error(f"清理浏览器临时环境失败: {e}")
        return count
    
    async def preload(self, keys: List[str]) -> int:
        """缓存预热（异步）
        
        将指定的键从L2加载到L1。
        
        Args:
            keys: 要预热的键列表
        
        Returns:
            成功预热的数量
        """
        count = 0
        for key in keys:
            value = await self.get(key)
            if value is not None:
                count += 1
        logger.info(f"缓存预热完成: {count}/{len(keys)}")
        return count
    
    async def cleanup_expired(self) -> int:
        """清理过期条目（异步）
        
        Returns:
            清理的条目数量
        """
        count = 0
        now = time.time()
        
        # 清理L1
        async with self._l1_lock:
            expired_keys = [
                key for key, entry in self._l1_cache.items()
                if now - entry['created_at'] >= entry['ttl']
            ]
            for key in expired_keys:
                del self._l1_cache[key]
                count += 1
        
        # 清理L2（支持 .json 和旧 .pkl 格式）
        try:
            for pattern in ("*.json", "*.pkl"):
                for cache_file in self.l2_cache_dir.glob(pattern):
                    try:
                        content = await self._file_storage.read_file(str(cache_file), "r")
                        entry = json.loads(content)
                        if now - entry['created_at'] >= entry['ttl']:
                            await self._file_storage.delete_file(str(cache_file))
                            count += 1
                    except Exception:
                        await self._file_storage.delete_file(str(cache_file))
                        count += 1
        except Exception as e:
            logger.error(f"清理L2过期条目失败: {e}", exc_info=True)
        
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息
        
        Returns:
            包含命中率等统计信息的字典
        """
        l1_total = self._l1_hits + self._l1_misses
        l2_total = self._l2_hits + self._l2_misses
        
        return {
            'l1_size': len(self._l1_cache),
            'l1_hits': self._l1_hits,
            'l1_misses': self._l1_misses,
            'l1_hit_rate': self._l1_hits / l1_total if l1_total > 0 else 0,
            'l2_hits': self._l2_hits,
            'l2_misses': self._l2_misses,
            'l2_hit_rate': self._l2_hits / l2_total if l2_total > 0 else 0,
        }

