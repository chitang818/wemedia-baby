from __future__ import annotations

import logging
import sys

from src.infrastructure.common.path_manager import PathManager
from src.infrastructure.monitoring.log_setup import init_log_manager

async def initialize_services_async() -> bool:
    """初始化所有服务（异步版本，新架构）
    
    Returns:
        如果初始化成功返回True，否则返回False
    """
    try:
        from src.utils.startup_profiler import mark
        mark("init_start")
        # 按需导入重型模块，避免启动时一次性加载
        from src.infrastructure.common.di.service_locator import ServiceLocator, Scope
        from src.infrastructure.common.event.event_bus import EventBus
        from src.infrastructure.common.cache.cache_manager import CacheManager
        from src.infrastructure.common.config.config_center import ConfigCenter
        from src.infrastructure.common.security.rbac import RBAC
        from src.infrastructure.common.security.encryption import EncryptionManager
        from src.infrastructure.storage.file_storage import AsyncFileStorage
        from src.infrastructure.network.http_client import AsyncHttpClient
        from src.services.publish.publish_service import PublishService
        from src.services.account.account_service import AccountService
        from src.services.subscription.subscription_service import SubscriptionService
        from src.infrastructure.common.pipeline.publish_pipeline import PublishPipeline
        from src.infrastructure.monitoring.metrics import MetricsCollector
        from src.infrastructure.monitoring.logger import StructuredLogger
        from src.infrastructure.monitoring.alerting import AlertManager
        from src.services.browser.playwright_service import PlaywrightBrowserService
        from src.infrastructure.storage.tortoise_manager import init_tortoise
        from src.domain.repositories import (
            AccountRepositoryAsync,
            UserRepositoryAsync,
            SubscriptionRepositoryAsync,
            PublishRecordRepositoryAsync,
            BatchTaskRepositoryAsync,
        )
        from src.infrastructure.common.pipeline.filters.execution_filter import PublishExecutionFilter
        from src.services.account.account_manager_async import AccountManagerAsync
        from src.services.subscription.permission_controller_async import PermissionControllerAsync as PermissionController
        from src.services.publish.pipeline.filters.permission_check_filter_async import PermissionCheckFilterAsync

        # 0. 数据迁移 (已移除)
        
        # 初始化日志管理器 (使用 AppData 下的 logs 目录)
        log_dir = str(PathManager.get_log_dir())
        log_manager = init_log_manager(log_dir=log_dir)
        mark("log_init_done")
        # 使用标准logging模块获取logger
        logger = logging.getLogger("main")
        logger.info("=" * 60)
        logger.info("🚀 媒小宝启动中...")
        logger.info("=" * 60)
        logger.info(f"📁 应用数据目录: {PathManager.get_app_data_dir()}")
        logger.info(f"📝 日志目录: {log_dir}")
        logger.info("")
        # 源码运行时提醒：完整技术日志在文件里，终端滚动不会丢记录
        if not getattr(sys, "frozen", False):
            try:
                from pathlib import Path as _Path

                _main_log = _Path(log_dir) / "qasync_app.log"
                _mirror_hint = ""
                import os as _os

                if _os.environ.get("WEMEDIA_MIRROR_CONSOLE", "").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                    "on",
                ):
                    _mirror_hint = f"\n  终端镜像: {_Path(log_dir) / 'console_mirror.log'}"
                print(
                    f"\n[媒小宝] 完整日志已写入文件（与终端是否滚屏无关）:\n"
                    f"  {_main_log.resolve()}{_mirror_hint}\n",
                    file=sys.stderr,
                )
            except Exception:
                pass

        def _cleanup_debug_screenshots_bg() -> None:
            try:
                from src.utils.debug_screenshots_cleanup import cleanup_debug_screenshots_older_than
                n = cleanup_debug_screenshots_older_than(days=7)
                if n:
                    logging.getLogger("main").info("已清理超过 7 天的诊断截图: %s 个文件", n)
            except Exception as e:
                logging.getLogger("main").debug("诊断截图后台清理跳过: %s", e)

        import threading
        threading.Thread(target=_cleanup_debug_screenshots_bg, daemon=True).start()
        
        # 拆分初始化任务
        logger.info("⚡开始并发加载组件与配置...")
        # 提取环境目录供各服务初始化使用
        db_path = str(PathManager.get_db_path())
        file_storage_path = str(PathManager.get_app_data_dir() / "data")
        cache_dir = str(PathManager.get_cache_dir())
        config_dir = str(PathManager.get_config_dir())
        
        service_locator = ServiceLocator()
        service_locator.register(type(log_manager), log_manager, scope=Scope.SINGLETON)
        
        # ----------------------------------------------------
        # 同步轻量级组件：Repository、基础内存模块、DI 组装等
        # ----------------------------------------------------
        
        account_repo = AccountRepositoryAsync()
        service_locator.register(AccountRepositoryAsync, account_repo, scope=Scope.SINGLETON)
        user_repo = UserRepositoryAsync()
        service_locator.register(UserRepositoryAsync, user_repo, scope=Scope.SINGLETON)
        subscription_repo = SubscriptionRepositoryAsync()
        service_locator.register(SubscriptionRepositoryAsync, subscription_repo, scope=Scope.SINGLETON)
        publish_record_repo = PublishRecordRepositoryAsync()
        service_locator.register(PublishRecordRepositoryAsync, publish_record_repo, scope=Scope.SINGLETON)
        batch_task_repo = BatchTaskRepositoryAsync()
        service_locator.register(BatchTaskRepositoryAsync, batch_task_repo, scope=Scope.SINGLETON)
        
        async_file_storage = AsyncFileStorage(file_storage_path)
        service_locator.register(AsyncFileStorage, async_file_storage, scope=Scope.SINGLETON)
        
        http_client = AsyncHttpClient()
        service_locator.register(AsyncHttpClient, http_client, scope=Scope.SINGLETON)
        
        event_bus = EventBus()
        service_locator.register(EventBus, event_bus, scope=Scope.SINGLETON)
        
        cache_manager = CacheManager(l2_cache_dir=cache_dir)
        service_locator.register(CacheManager, cache_manager, scope=Scope.SINGLETON)
        
        rbac = RBAC()
        service_locator.register(RBAC, rbac, scope=Scope.SINGLETON)
        
        encryption_manager = EncryptionManager()
        service_locator.register(EncryptionManager, encryption_manager, scope=Scope.SINGLETON)
        
        # 管道并发上限与执行器层 PublishExecutor 的 max_concurrent=3 对齐，
        # 避免管道槽(5)多于执行器槽(3)导致批量场景下槽位空占浪费
        publish_pipeline = PublishPipeline(max_concurrent=3)
        browser_account_manager = AccountManagerAsync(user_id=1, event_bus=event_bus)
        permission_controller = PermissionController(
            user_repo=service_locator.get(UserRepositoryAsync),
            sub_repo=service_locator.get(SubscriptionRepositoryAsync),
        )
        from src.services.common.media_validator import MediaValidator
        from src.services.publish.pipeline.filters.media_validate_filter_async import MediaValidateFilterAsync
        from src.services.publish.pipeline.filters.account_load_filter_async import AccountLoadFilterAsync
        from src.services.publish.pipeline.filters.record_save_filter_async import RecordSaveFilterAsync

        publish_pipeline.add_filter(PermissionCheckFilterAsync(permission_controller))
        publish_pipeline.add_filter(MediaValidateFilterAsync(MediaValidator()))
        publish_pipeline.add_filter(AccountLoadFilterAsync(browser_account_manager))
        publish_pipeline.add_filter(PublishExecutionFilter())
        publish_pipeline.add_filter(RecordSaveFilterAsync(publish_record_repo))
        service_locator.register(PublishPipeline, publish_pipeline, scope=Scope.SINGLETON)
        
        publish_service = PublishService()
        service_locator.register(PublishService, publish_service, scope=Scope.SINGLETON)
        
        account_service = AccountService()
        service_locator.register(AccountService, account_service, scope=Scope.SINGLETON)
        
        subscription_service = SubscriptionService()
        service_locator.register(SubscriptionService, subscription_service, scope=Scope.SINGLETON)
        
        playwright_browser_service = PlaywrightBrowserService(browser_account_manager)
        service_locator.register(PlaywrightBrowserService, playwright_browser_service, scope=Scope.SINGLETON)
        
        metrics_collector = MetricsCollector()
        service_locator.register(MetricsCollector, metrics_collector, scope=Scope.SINGLETON)
        
        structured_logger = StructuredLogger()
        service_locator.register(StructuredLogger, structured_logger, scope=Scope.SINGLETON)
        
        alert_manager = AlertManager()
        service_locator.register(AlertManager, alert_manager, scope=Scope.SINGLETON)
        
        mark("di_light_done")
        logger.info("✅ 1/2 轻量组件注入完毕")
        
        # ----------------------------------------------------
        # 并发执行耗时任务 (IO 或密集型等)
        # ----------------------------------------------------
        config_center = ConfigCenter(config_dir=config_dir)
        service_locator.register(ConfigCenter, config_center, scope=Scope.SINGLETON)
        
        import asyncio
        async def wrapped_tortoise():
            mark("orm_start")
            await init_tortoise(db_path)
            mark("orm_done")
        async def wrapped_config():
            mark("config_start")
            await config_center.initialize()
            mark("config_done")
        mark("gather_start")
        init_tasks = [
            wrapped_tortoise(),
            wrapped_config(),
        ]
        await asyncio.gather(*init_tasks)
        mark("gather_done")
        logger.info("✅ 2/2 模块配置、ORM 初始化完成（插件与浏览器延后至主窗口显示后加载）")

        async def _background_material_library_sync():
            try:
                from src.infrastructure.common.material_library_manager import MaterialLibraryManager

                await MaterialLibraryManager.sync_platform_account_tree()
            except Exception as e:
                logger.debug("启动后同步媒体库目录树跳过或失败（可忽略）: %s", e)

        from src.infrastructure.common.async_task_registry import get_async_task_registry
        get_async_task_registry().create_task(
            _background_material_library_sync(),
            name="startup.material_library_sync",
            group="startup",
        )
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ 所有服务初始化成功! Application ready!")
        logger.info("=" * 60)
        return True
        
    except Exception as e:
        logging.error(f"服务初始化失败: {e}", exc_info=True)
        return False


