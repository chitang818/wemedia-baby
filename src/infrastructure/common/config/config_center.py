"""
配置中心模块（优化版）
文件路径：src/infrastructure/common/config/config_center.py
功能：统一管理所有配置文件，支持本地 JSON、热更新；远程拉取与内存版本链为可选扩展能力。

桌面应用（main 注入单例）当前仅使用：本地 ``app_config.json``、文件监控热更新、
``merge_app_config`` / ``update`` 写盘。``remote_config_url`` 默认为 None，不会发起远程轮询；
``rollback()`` / ``watch_changes`` 保留给将来或工具链使用，产品内暂无 UI。
"""

import copy
import json
import asyncio
from typing import Dict, Any, Optional, List, Callable, Union
from pathlib import Path
import logging
from datetime import datetime
import hashlib

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.infrastructure.network.http_client import AsyncHttpClient
from src.infrastructure.storage.file_storage import AsyncFileStorage
from src.infrastructure.common.config.app_config_defaults import (
    apply_app_config_defaults_inplace,
)
from src.infrastructure.common.config.app_config_merge import (
    APP_CONFIG_FILENAME,
    _deep_merge_inplace,
)
from src.infrastructure.common.async_task_registry import get_async_task_registry

logger = logging.getLogger(__name__)


def get_registered_config_center() -> Optional["ConfigCenter"]:
    """获取已在 ServiceLocator 注册的 ConfigCenter 单例（应用正常运行时始终存在）。"""
    try:
        from src.infrastructure.common.di.service_locator import ServiceLocator

        return ServiceLocator().get_optional(ConfigCenter)
    except Exception:
        return None


class ConfigVersionManager:
    """配置版本管理器
    
    管理配置的版本历史，支持配置回滚。
    """
    
    def __init__(self, max_versions: int = 5):
        """初始化配置版本管理器
        
        Args:
            max_versions: 保留的最大版本数
        """
        self.max_versions = max_versions
        self.versions: Dict[str, List[Dict[str, Any]]] = {}  # config_key -> [versions]
    
    def save_version(self, config_key: str, config_data: Dict[str, Any]) -> int:
        """保存配置版本
        
        Args:
            config_key: 配置键
            config_data: 配置数据
        
        Returns:
            版本号
        """
        if config_key not in self.versions:
            self.versions[config_key] = []
        
        version = {
            'version': len(self.versions[config_key]) + 1,
            'timestamp': datetime.now().isoformat(),
            'data': config_data.copy(),
            'hash': self._calculate_hash(config_data)
        }
        
        self.versions[config_key].append(version)
        
        # 只保留最近max_versions个版本
        if len(self.versions[config_key]) > self.max_versions:
            self.versions[config_key] = self.versions[config_key][-self.max_versions:]
        
        return version['version']
    
    def get_version(self, config_key: str, version: int) -> Optional[Dict[str, Any]]:
        """获取指定版本的配置
        
        Args:
            config_key: 配置键
            version: 版本号
        
        Returns:
            配置数据，如果版本不存在返回None
        """
        if config_key not in self.versions:
            return None
        
        for v in self.versions[config_key]:
            if v['version'] == version:
                return v['data']
        
        return None
    
    def get_latest_version(self, config_key: str) -> Optional[Dict[str, Any]]:
        """获取最新版本的配置
        
        Args:
            config_key: 配置键
        
        Returns:
            最新配置数据，如果不存在返回None
        """
        if config_key not in self.versions or not self.versions[config_key]:
            return None
        
        return self.versions[config_key][-1]['data']
    
    def _calculate_hash(self, data: Dict[str, Any]) -> str:
        """计算配置数据的哈希值
        
        Args:
            data: 配置数据
        
        Returns:
            哈希值
        """
        content = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content.encode()).hexdigest()


class ConfigFileHandler(FileSystemEventHandler):
    """配置文件变化处理器"""
    
    def __init__(self, callback: Callable[[str], None]):
        """初始化处理器
        
        Args:
            callback: 文件变化时的回调函数
        """
        self.callback = callback
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self.callback(event.src_path)


class ConfigCenter:
    """配置中心 - 统一管理所有配置文件（优化版）

    生产路径以本地 JSON + 可选文件热更新为主。传入 ``remote_config_url`` 时才会加载/轮询远程配置；
    ``ConfigVersionManager`` 在每次更新时记录内存版本，``rollback()`` 可回写到文件（无内置设置界面）。
    """
    
    def __init__(
        self,
        config_dir: Optional[Union[str, Path]] = None,
        remote_config_url: Optional[str] = None,
        poll_interval: int = 60
    ):
        """初始化配置中心
        
        Args:
            config_dir: 配置目录路径；默认 None 时使用 PathManager.get_config_dir()（与用户数据目录一致），
                避免打包后 cwd 在安装目录时误用「安装目录/config」与主程序注册的实例读写分离。
            remote_config_url: 远程配置 URL；桌面版默认 None，不启用 HTTP 拉取与轮询。
            poll_interval: 远程轮询间隔（秒），仅当 ``remote_config_url`` 非空时有效。
        """
        if config_dir is None:
            from src.infrastructure.common.path_manager import PathManager

            self.config_dir = PathManager.get_config_dir()
        else:
            self.config_dir = Path(config_dir)
        self.remote_config_url = remote_config_url
        self.poll_interval = poll_interval
        
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._version_manager = ConfigVersionManager(max_versions=5)
        self._change_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        
        self._http_client = AsyncHttpClient()
        self._file_storage = AsyncFileStorage(str(self.config_dir))
        
        # 获取当前事件循环
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
            logger.warning("ConfigCenter initialized without running event loop")
        
        # 文件监控
        self._observer: Optional[Observer] = None
        # 热更新去抖：同一 config_key 在短时间内多次变更只执行一次重载
        self._reload_debounce_tasks: Dict[str, asyncio.Task] = {}
        self._reload_debounce_seconds = 0.4
        
        # 确保配置目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 任务控制
        self._load_task = None
        self._poll_task = None

        # 串行化 app_config 写盘，避免 merge/update 并发导致 lost update
        self._app_config_write_lock = asyncio.Lock()
        # 无配置文件、或磁盘 JSON 缺键经内存补齐后，在 initialize 末尾落盘一次
        self._app_config_skeleton_persist_pending = False

        # 注意：不在此处自动启动加载，应在 initialize() 中显式调用并等待
        # 这样可以确保在使用配置前已完成加载
        # self._load_task = asyncio.create_task(self._load_all_configs())
        
        # 启动文件监控
        self._start_file_watcher()
        # 远程配置轮询在 initialize() 中统一启动，避免 __init__ 阶段重复创建任务
    
    async def _load_all_configs(self) -> None:
        """加载所有配置（异步）"""
        try:
            await self._load_local_configs()
            if self.remote_config_url:
                await self._load_remote_configs()
        except Exception as e:
            logger.error(f"加载配置失败: {e}", exc_info=True)
    
    async def initialize(self) -> None:
        """初始化配置中心（异步）"""
        # 加载配置
        if self._load_task is None:
            self._load_task = get_async_task_registry().create_task(
                self._load_all_configs(),
                name="config.load_all",
                group="config",
            )
            await self._load_task

        if self._app_config_skeleton_persist_pending:
            self._app_config_skeleton_persist_pending = False
            await self.update(
                "app_config", copy.deepcopy(self.get_app_config())
            )
        
        # 启动远程配置轮询
        if self.remote_config_url and self._poll_task is None:
            self._poll_task = get_async_task_registry().create_task(
                self._poll_remote_config(),
                name="config.remote_poll",
                group="config",
            )
    
    async def _load_local_configs(self) -> None:
        """加载本地配置（异步）"""
        config_files = [
            ("app_config", "app_config.json"),
        ]
        
        for config_key, config_file in config_files:
            # AsyncFileStorage 已经配置了 base_path，所以这里不需要拼接 config_dir
            # 使用相对路径，AsyncFileStorage 会自动处理
            config_path = config_file
            exists = await self._file_storage.file_exists(str(config_path))
            if not exists:
                if config_key == "app_config":
                    self._configs[config_key] = {}
                    if apply_app_config_defaults_inplace(self._configs[config_key]):
                        self._app_config_skeleton_persist_pending = True
                    self._version_manager.save_version(
                        config_key, copy.deepcopy(self._configs[config_key])
                    )
                    logger.debug("本地无 app_config.json，已载入默认骨架（待首次落盘）")
                continue
            try:
                content = await self._file_storage.read_file(str(config_path), "r")
                config_data = json.loads(content)
                if not isinstance(config_data, dict):
                    logger.warning(
                        "本地配置格式异常（应为 JSON 对象），已按空对象处理: %s",
                        config_key,
                    )
                    config_data = {}
                self._configs[config_key] = config_data
                if apply_app_config_defaults_inplace(self._configs[config_key]):
                    self._app_config_skeleton_persist_pending = True
                self._version_manager.save_version(
                    config_key, copy.deepcopy(self._configs[config_key])
                )
                logger.debug(f"加载本地配置成功: {config_key}")
            except Exception as e:
                logger.error(f"加载本地配置失败: {config_key}, 错误: {e}", exc_info=True)

        if "app_config" not in self._configs:
            self._configs["app_config"] = {}
            if apply_app_config_defaults_inplace(self._configs["app_config"]):
                self._app_config_skeleton_persist_pending = True
            self._version_manager.save_version(
                "app_config", copy.deepcopy(self._configs["app_config"])
            )
    
    async def _load_remote_configs(self) -> None:
        """加载远程配置（异步）"""
        try:
            response = await self._http_client.get(self.remote_config_url)
            if isinstance(response, dict):
                for key, value in response.items():
                    self._configs[key] = value
                    # 保存版本
                    self._version_manager.save_version(key, value)
                logger.debug("加载远程配置成功")
        except Exception as e:
            logger.error(f"加载远程配置失败: {e}", exc_info=True)
    
    def _start_file_watcher(self) -> None:
        """启动文件监控"""
        try:
            self._observer = Observer()
            handler = ConfigFileHandler(self._on_config_file_changed)
            self._observer.schedule(handler, str(self.config_dir), recursive=True)
            self._observer.start()
            logger.debug("配置文件监控已启动")
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}", exc_info=True)
    
    def _on_config_file_changed(self, file_path: str) -> None:
        """配置文件变化回调
        
        Args:
            file_path: 变化的文件路径
        """
        # 确定配置键
        config_key = None
        if file_path.endswith("app_config.json"):
            config_key = "app_config"
        
        if config_key and hasattr(self, '_loop') and self._loop:
            # 异步调度去抖重载（跨线程）
            abs_file_path = str(Path(file_path).resolve())
            asyncio.run_coroutine_threadsafe(
                self._schedule_debounced_reload(config_key, abs_file_path),
                self._loop
            )
    
    async def _schedule_debounced_reload(self, config_key: str, file_path: str) -> None:
        """调度带去抖的配置重载：短时间多次变更只执行一次 _reload_config。"""
        if config_key in self._reload_debounce_tasks:
            self._reload_debounce_tasks[config_key].cancel()
        async def run() -> None:
            try:
                await asyncio.sleep(self._reload_debounce_seconds)
            except asyncio.CancelledError:
                self._reload_debounce_tasks.pop(config_key, None)
                raise
            self._reload_debounce_tasks.pop(config_key, None)
            await self._reload_config(config_key, file_path)
        self._reload_debounce_tasks[config_key] = get_async_task_registry().create_task(
            run(),
            name=f"config.reload_debounce.{config_key}",
            group="config",
        )
    
    async def _reload_config(self, config_key: str, file_path: str) -> None:
        """重新加载配置（异步）
        
        Args:
            config_key: 配置键
            file_path: 配置文件路径
        """
        try:
            # 文件监听在「写入中」会触发多次事件，此时内容可能为空或 JSON 还未写完整
            # 这里做容错：空内容直接忽略；JSON 解析失败短暂重试几次
            content = await self._file_storage.read_file(file_path, "r")
            if not content or not str(content).strip():
                logger.debug(f"跳过热更新：配置内容为空: {config_key}, path={file_path}")
                return

            config_data = None
            last_err: Exception | None = None
            for retry_delay in (0.05, 0.1, 0.2):
                try:
                    config_data = json.loads(content)
                    break
                except json.JSONDecodeError as e:
                    last_err = e
                    await asyncio.sleep(retry_delay)
                    content = await self._file_storage.read_file(file_path, "r")
                    if not content or not str(content).strip():
                        logger.debug(f"跳过热更新：配置内容为空(重试后): {config_key}, path={file_path}")
                        return

            if config_data is None:
                raise last_err or ValueError("配置解析失败")

            async def _apply_reload() -> None:
                data = config_data
                if config_key == "app_config":
                    if not isinstance(data, dict):
                        data = {}
                    apply_app_config_defaults_inplace(data)
                    self._configs[config_key] = data
                    self._version_manager.save_version(
                        config_key, copy.deepcopy(data)
                    )
                    for callback in self._change_callbacks:
                        try:
                            callback(config_key, data)
                        except Exception as e:
                            logger.error(
                                f"执行配置变化回调失败: {e}", exc_info=True
                            )
                    return
                self._configs[config_key] = data
                self._version_manager.save_version(config_key, data)
                for callback in self._change_callbacks:
                    try:
                        callback(config_key, data)
                    except Exception as e:
                        logger.error(f"执行配置变化回调失败: {e}", exc_info=True)

            if config_key == "app_config":
                async with self._app_config_write_lock:
                    await _apply_reload()
            else:
                await _apply_reload()

            logger.debug("配置热更新成功: %s", config_key)
        except Exception as e:
            logger.error(f"重新加载配置失败: {config_key}, 错误: {e}", exc_info=True)
    
    async def _poll_remote_config(self) -> None:
        """轮询远程配置（异步）"""
        while True:
            try:
                await asyncio.sleep(self.poll_interval)
                await self._load_remote_configs()
            except Exception as e:
                logger.error(f"轮询远程配置失败: {e}", exc_info=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（支持分类管理，如storage.db_path）
        
        Args:
            key: 配置键，支持点号分隔（如storage.db_path）
            default: 默认值
        
        Returns:
            配置值，如果不存在返回默认值
        """
        keys = key.split('.')
        value = self._configs
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value
    
    def get_app_config(self) -> Dict[str, Any]:
        """获取应用配置（始终返回内存中的同一 dict，禁止依赖「未命中时默认 {}」的临时对象）。

        说明：若使用 ``_configs.get("app_config", {})``，在键不存在时每次会得到新的空 dict，
        且 ``get_app_config() or {}`` 在配置为空 dict 时会错误地再换用另一个 dict，
        导致读写不是同一份数据、持久化字段（如 material_library_root）表现异常。
        """
        if "app_config" not in self._configs:
            self._configs["app_config"] = {}
        cfg = self._configs["app_config"]
        if not isinstance(cfg, dict):
            self._configs["app_config"] = {}
            return self._configs["app_config"]
        return cfg
    
    def get_platform_config(self, platform_name: str) -> Optional[Dict[str, Any]]:
        """获取平台配置
        
        Args:
            platform_name: 平台名称
        
        Returns:
            平台配置字典，如果不存在返回None
        """
        return self._configs.get(f"platform_{platform_name}")
    
    async def update(self, key: str, value: Any) -> None:
        """更新配置值（异步）
        
        Args:
            key: 配置键
            value: 配置值
        """
        if key == "app_config":
            async with self._app_config_write_lock:
                await self._update_unlocked(
                    key, value, merge_app_config_with_disk=True
                )
        else:
            await self._update_unlocked(key, value)

    def _read_app_config_from_disk_sync(self) -> Dict[str, Any]:
        """读取当前 ConfigCenter 目录下的 app_config.json（与写盘路径一致）。"""
        p = self.config_dir / APP_CONFIG_FILENAME
        if not p.is_file():
            return {}
        try:
            raw = p.read_text(encoding="utf-8")
            if not str(raw).strip():
                return {}
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.debug("读取磁盘 app_config 失败: %s", e)
            return {}

    async def _update_unlocked(
        self,
        key: str,
        value: Any,
        *,
        merge_app_config_with_disk: bool = False,
    ) -> None:
        """执行更新与写盘（app_config 路径由 update() / rollback() 持锁后调用）。"""
        prev = self._configs.get(key)
        if key == "app_config" and isinstance(prev, dict):
            old_data = copy.deepcopy(prev)
        elif isinstance(prev, dict):
            old_data = prev.copy()
        else:
            old_data = {}
        self._version_manager.save_version(key, old_data)

        if (
            key == "app_config"
            and merge_app_config_with_disk
            and isinstance(value, dict)
        ):
            disk_data = self._read_app_config_from_disk_sync()
            if disk_data:
                merged = copy.deepcopy(disk_data)
                _deep_merge_inplace(merged, value)
                value = merged

        self._configs[key] = value

        config_path = f"{key}.json"

        content = json.dumps(value, indent=2, ensure_ascii=False)
        await self._file_storage.write_file(str(config_path), content, "w")

        logger.info(f"配置更新成功: {key}")
    
    async def rollback(self, config_key: str, version: int) -> bool:
        """回滚到指定版本（异步）
        
        Args:
            config_key: 配置键
            version: 版本号
        
        Returns:
            如果回滚成功返回True，否则返回False
        """
        config_data = self._version_manager.get_version(config_key, version)
        if config_data is None:
            logger.warning(f"配置版本不存在: {config_key}, version={version}")
            return False

        if config_key == "app_config":
            async with self._app_config_write_lock:
                await self._update_unlocked(
                    config_key, config_data, merge_app_config_with_disk=False
                )
        else:
            await self._update_unlocked(config_key, config_data)
        logger.info(f"配置回滚成功: {config_key}, version={version}")
        return True
    
    def watch_changes(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """监听配置变化
        
        Args:
            callback: 配置变化回调函数 (config_key, config_data) -> None
        """
        self._change_callbacks.append(callback)
    
    async def reload(self) -> None:
        """重新加载所有配置（异步）"""
        await self._load_all_configs()
        logger.info("重新加载所有配置完成")
    
    def close(self) -> None:
        """关闭配置中心"""
        for task in (
            self._load_task,
            self._poll_task,
            *list(self._reload_debounce_tasks.values()),
        ):
            if task and not task.done():
                task.cancel()
        self._reload_debounce_tasks.clear()

        if self._observer:
            self._observer.stop()
            self._observer.join()
        # 关闭HTTP客户端：有事件循环时用 run_coroutine_threadsafe + 超时等待，确保会话干净释放
        if self._http_client:
            try:
                loop = asyncio.get_running_loop()
                future = asyncio.run_coroutine_threadsafe(self._http_client.close(), loop)
                try:
                    future.result(timeout=3)
                except Exception as e:
                    logger.warning(f"关闭HTTP客户端超时或失败: {e}")
            except RuntimeError:
                try:
                    asyncio.run(self._http_client.close())
                except Exception as e:
                    logger.warning(f"关闭HTTP客户端失败: {e}")

