

import logging
from typing import Optional, Dict, Any
from src.infrastructure.common.async_task_registry import get_async_task_registry
from src.infrastructure.common.config.config_center import ConfigCenter, get_registered_config_center
from .browser_manager import UndetectedBrowserManager
from .process_supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)

def _ensure_chrome_path_configured() -> None:
    """若未配置 chrome_executable_path，则自动检测并写入 app_config（同步尽力而为）。

    必须使用已注册的 ConfigCenter，且在异步写入前 await initialize() 再合并，
    避免历史上「空 get_app_config() + 整文件 update」冲掉 material_library_root 等同文件其它键。
    """
    try:
        cc = get_registered_config_center()
        if cc is None:
            logger.debug("ConfigCenter 未注册，跳过 chrome 路径自动写入")
            return
        app = {**cc.get_app_config()}
        p = app.get("chrome_executable_path")
        if isinstance(p, str) and p.strip():
            return
        from src.utils.chrome_installer import detect_chrome
        installed, info = detect_chrome()
        if not installed:
            logger.warning("未检测到系统已安装的 Google Chrome（将依赖设置页安装/配置）")
            return
        path = (info or {}).get("path")
        if not path:
            logger.warning("已检测到 Chrome 但未能解析可执行路径（info=%s）", info)
            return
        # ConfigCenter.update 是 async；这里处于同步工厂，采用“尽力写入”，不阻塞主流程
        import asyncio

        async def _upd():
            await cc.initialize()
            merged = {**cc.get_app_config()}
            merged["chrome_executable_path"] = path
            await cc.update("app_config", merged)

        try:
            loop = asyncio.get_running_loop()
            get_async_task_registry().create_task(
                _upd(),
                name="browser_factory.persist_chrome_path",
                group="browser",
            )
            logger.info("已自动写入 chrome_executable_path 到 app_config: %s", path)
        except RuntimeError:
            # 同步环境（无运行中的 event loop）下不再强行 asyncio.run，避免在 GUI/嵌套循环场景引发问题
            logger.warning("当前无运行中的事件循环，跳过自动写入 chrome_executable_path（path=%s）", path)
    except Exception as e:
        logger.warning("自动检测/写入 chrome_executable_path 失败（忽略，不影响继续启动）: %s", e, exc_info=True)
        return


class BrowserFactory:
    """浏览器工厂
    
    根据配置返回对应的浏览器管理器实例。
    每个账号对应一个独立的管理器实例。
    """
    
    _initialized: bool = False
    
    @classmethod
    def _ensure_initialized(cls):
        """确保 ProcessSupervisor 已初始化，并在后台预热 Playwright 环境（一次性）。"""
        if not cls._initialized:
            ProcessSupervisor.initialize()
            cls._initialized = True
            # 浏览器环境预热：不阻塞当前调用，仅尽力而为，加快用户首次双击账号时的启动速度
            try:
                import asyncio
                # 若当前已有事件循环在运行（例如 qasync 主循环），则在其中调度预热任务
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    get_async_task_registry().create_task(
                        UndetectedBrowserManager.ensure_warmup(),
                        name="browser_factory.warmup",
                        group="browser",
                    )
            except Exception:
                # 预热失败不影响正常功能，静默忽略
                logger.debug("BrowserFactory 预热浏览器环境失败（忽略，不影响正常使用）", exc_info=True)
    
    @staticmethod
    def get_browser_service(
        account_id: str, 
        platform: str = "", 
        platform_username: str = "",
        fingerprint_config: Optional[dict] = None,  # 新增参数,使用小写dict
        profile_folder_name: Optional[str] = None
    ) -> UndetectedBrowserManager:
        """获取浏览器服务实例
        
        Args:
            account_id: 账号唯一标识
            platform: 平台名称 (如 douyin)
            platform_username: 平台用户名
            fingerprint_config: 指纹配置,None则随机生成
            profile_folder_name: 持久化环境名称
        
        Returns:
            UndetectedBrowserManager 实例
        """
        BrowserFactory._ensure_initialized()
        _ensure_chrome_path_configured()
        
        config_center = get_registered_config_center() or ConfigCenter()
        app_config = config_center.get_app_config()
        scheme = app_config.get("browser_scheme", "playwright")
        
        logger.info(f"浏览器工厂: scheme={scheme}, account={platform_username}, platform={platform}")
        
        # 统一使用 UndetectedBrowserManager
        return UndetectedBrowserManager(
            account_id, 
            platform, 
            platform_username,
            fingerprint_config=fingerprint_config,  # 传递指纹配置
            profile_folder_name=profile_folder_name
        )
    
    @staticmethod
    def get_browser_manager(account_id: str) -> UndetectedBrowserManager:
        """获取浏览器管理器 (get_browser_service 的别名)
        
        Args:
            account_id: 账号唯一标识
            
        Returns:
            UndetectedBrowserManager 实例
        """
        return BrowserFactory.get_browser_service(account_id)

