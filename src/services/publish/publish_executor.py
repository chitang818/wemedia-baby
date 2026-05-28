"""
发布执行器
文件路径：src/services/publish/publish_executor.py
功能：集成 UndetectedBrowserManager 与发布管道，管理浏览器生命周期
"""

from typing import Dict, Any, Optional, List
import logging
import asyncio

from src.infrastructure.common.pipeline.base_filter import PublishContext, PipelineResult, PipelineResult as PublishResult
from src.utils.date_utils import format_schedule_time_st_str

logger = logging.getLogger(__name__)


class PublishExecutor:
    """发布执行器 - 集成浏览器管理与发布流程
    
    职责:
    1. 启动浏览器并加载账号凭证
    2. 将浏览器/页面实例注入 PublishContext
    3. 执行发布管道
    4. 管理浏览器生命周期
    """
    
    def __init__(
        self,
        user_id: int,
        data_storage=None,
        max_concurrent: int = 3
    ):
        """初始化发布执行器
        
        Args:
            user_id: 用户ID
            data_storage: 数据存储实例（可选）
            max_concurrent: 最大并发数
        """
        self.user_id = user_id
        self.data_storage = data_storage
        self.max_concurrent = max_concurrent
        
        self._semaphore = asyncio.Semaphore(max_concurrent)
    
    async def execute_single(
        self,
        account_name: str,
        platform: str,
        file_path: str,
        title: str = "",
        description: str = "",
        tags: Optional[List[str]] = None,
        file_type: str = "video",
        headless: bool = True,
        speed_rate: float = 1.0,
        pause_event: Any = None,
        scheduled_publish_time: Optional[Any] = None,
        privacy_settings: Optional[str] = None,
        cover_type: Optional[str] = None,
        cover_path: Optional[str] = None,
        close_browser_after: bool = True,
        poi_info: Optional[str] = None,
        wechat_empty_location_open_picker: Optional[bool] = None,
        cart_info: Optional[str] = None,
        anchor_info: Optional[str] = None,
        micro_app_info: Optional[str] = None,
        music_info: Optional[str] = None,
    ) -> PublishResult:
        """执行单个发布任务
        
        Args:
            account_name: 账号名称（用作 account_id）
            platform: 平台ID
            file_path: 文件路径
            title: 标题
            description: 描述
            tags: 标签列表
            file_type: 文件类型 (video/image)
            headless: 是否使用无头模式
            speed_rate: 发布速度倍率
            pause_event: 暂停控制事件
            
        Returns:
            发布结果
        """
        browser_manager = None
        context = None
        page = None
        result = None  # 初始化 result 用于 finally 块判断
        account_db_id = None  # 提前初始化，防止 finally 中访问时因提前 return 而 NameError
        
        try:
            async with self._semaphore:
                # 按需预热 Playwright（进程内仅一次，减少首次发布等待）
                try:
                    from src.infrastructure.browser.browser_manager import UndetectedBrowserManager
                    await UndetectedBrowserManager.ensure_warmup()
                except Exception:
                    pass
                # Step 1: 获取 PlaywrightBrowserService 单例
                from src.infrastructure.common.di.service_locator import ServiceLocator
                
                pw_service = ServiceLocator().get("PlaywrightBrowserService")
                if not pw_service or not pw_service.account_manager:
                    return PublishResult(success=False, error_message="PlaywrightBrowserService 未初始化，无法启动浏览器")
                
                account_mgr = pw_service.account_manager
                
                # Step 2: 通过 account_name + platform 查找数据库中的账号ID
                account_db_id = None
                try:
                    all_accounts = await account_mgr.get_accounts(platform=platform)
                    for a in all_accounts:
                        name = a.get('platform_username') or a.get('account_name', '') if isinstance(a, dict) else getattr(a, 'platform_username', '')
                        if name == account_name:
                            account_db_id = a.get('id') if isinstance(a, dict) else getattr(a, 'id', None)
                            break
                except Exception as e:
                    logger.error(f"查询账号列表失败（关键路径）: {e}")
                    return PublishResult(success=False, error_message=f"查询账号列表失败: {e}")
                
                if not account_db_id:
                    return PublishResult(success=False, error_message=f"未在数据库中找到账号: {account_name} (平台: {platform})")
                
                logger.info(f"发布任务: 账号={account_name}, 数据库ID={account_db_id}, 平台={platform}")
                if str(platform).strip().lower() == "xiaohongshu" and headless:
                    logger.info("小红书 strict_real_browser：发布流程强制使用可见浏览器")
                    headless = False
                
                # Step 3: 复用模块化方法打开浏览器（headless 与发布页「显示浏览器」勾选一致）
                browser_wrapper = await pw_service.open_browser_for_db_account(
                    account_db_id,
                    headless=headless,
                    maximize_for_publish=True,
                )
                if not browser_wrapper or not browser_wrapper.context:
                    return PublishResult(success=False, error_message="未能正确拉起或获取浏览器组件实例")
                    
                browser_context = browser_wrapper.context
                page = browser_wrapper.page
                browser_manager = browser_wrapper.browser_manager

                # 有头模式下环境信息为第二标签；启动/刷新环境页后 Chrome 可能仍停在环境标签，发布前强制聚焦第一标签（业务页）
                if not headless and browser_manager and hasattr(browser_manager, "focus_first_tab_for_ui"):
                    try:
                        await browser_manager.focus_first_tab_for_ui()
                    except Exception as _focus_e:
                        logger.debug("发布前聚焦业务标签页失败(可忽略): %s", _focus_e)
                if browser_manager and hasattr(browser_manager, "refresh_environment_page_ref"):
                    try:
                        await browser_manager.refresh_environment_page_ref()
                    except Exception:
                        pass
                if browser_manager and hasattr(browser_manager, "pick_business_page_for_automation"):
                    try:
                        best = browser_manager.pick_business_page_for_automation()
                        if best is not None and not best.is_closed():
                            page = best
                            browser_wrapper.page = best
                            if hasattr(browser_manager, "note_primary_work_page"):
                                browser_manager.note_primary_work_page(best)
                    except Exception:
                        pass

                logger.info("发布所用浏览器拉取成功")
                
                # Step 4: 创建发布上下文
                context = PublishContext(
                    user_id=self.user_id,
                    account_name=account_name,
                    platform=platform,
                    file_path=file_path,
                    file_type=file_type,
                    publish_type=file_type,  # 与 file_type 保持一致，供插件判断图文/视频
                    title=title,
                    description=description,
                    tags=tags or [],
                    headless=headless,
                    speed_rate=speed_rate,
                    pause_event=pause_event,
                    scheduled_publish_time=scheduled_publish_time,
                    privacy_settings=privacy_settings,
                    cover_type=cover_type,
                    cover_path=cover_path,
                    poi_info=poi_info,
                    wechat_empty_location_open_picker=wechat_empty_location_open_picker,
                    cart_info=cart_info,
                    anchor_info=anchor_info,
                    micro_app_info=micro_app_info,
                    music_info=music_info,
                )
                
                # 注入浏览器实例到上下文
                context.browser = browser_context
                context.page = page
                context.browser_manager = browser_manager
                
                # Step 5: 获取平台适配器并执行发布
                logger.info(f"开始执行平台发布逻辑: platform={platform}")
                result = await self._execute_platform_publish(context, platform)
                logger.info(f"平台发布逻辑执行结束: success={result.success}")
                
                # Step 6: 保存发布后的状态
                if result.success:
                    if browser_manager and hasattr(browser_manager, 'save_state'):
                        await browser_manager.save_state()
                    logger.info(f"发布成功: {result.publish_url}")
                else:
                    logger.warning(f"发布失败，保持浏览器打开以便用户查看: {result.error_message}")
                
                return result
                
        except Exception as e:
            logger.error(f"发布执行失败: {e}", exc_info=True)
            return PublishResult(
                success=False,
                error_message=str(e)
            )
        finally:
            if close_browser_after and account_db_id:
                try:
                    from src.infrastructure.common.di.service_locator import ServiceLocator
                    pw_svc = ServiceLocator().get("PlaywrightBrowserService")
                    if pw_svc:
                        await pw_svc.close_browser(str(account_db_id))
                except Exception as e:
                    logger.warning("通过 PlaywrightBrowserService 关闭浏览器异常: %s", e)
                    if page:
                        try:
                            await page.close()
                        except Exception as e2:
                            logger.warning("关闭 page 时异常: %s", e2)
                    if browser_manager:
                        try:
                            await browser_manager.close()
                        except Exception as e2:
                            logger.warning("关闭 browser_manager 时异常: %s", e2)
                    # 兜底：若上述所有关闭路径都失败，按 user_data_dir 特征强杀残留进程
                    if browser_manager and hasattr(browser_manager, '_force_kill_browser_process'):
                        try:
                            await browser_manager._force_kill_browser_process()
                        except Exception as e3:
                            logger.warning("兜底强杀浏览器进程异常: %s", e3)
    
    async def _execute_platform_publish(
        self,
        context: PublishContext,
        platform: str
    ) -> PublishResult:
        """执行平台特定的发布逻辑
        
        Args:
            context: 发布上下文（已包含浏览器实例）
            platform: 平台ID
            
        Returns:
            发布结果
        """
        try:
            # 平台启用校验：避免通过非 UI 入口绕过禁用平台
            try:
                from src.utils.plugin_settings import is_platform_enabled
                if not is_platform_enabled(platform):
                    return PublishResult(
                        success=False,
                        error_message=f"平台已禁用：{platform}（请在 设置-插件配置 中启用）"
                    )
            except Exception:
                pass

            # 获取平台发布插件 (统一使用 src.plugins.core.plugin_manager)
            from src.plugins.core.plugin_manager import PluginManager
            
            plugin = PluginManager.get_publish_plugin(platform)
            
            if not plugin:
                return PublishResult(
                    success=False,
                    error_message=f"未找到平台插件: {platform}"
                )
            
            # 调用插件发布方法 (使用新接口 async publish)；定时时间统一格式化为 YYYY-MM-DD HH:mm 字符串
            st_str = format_schedule_time_st_str(getattr(context, "scheduled_publish_time", None))
            metadata = {
                "title": context.title,
                "description": context.description,
                "tags": context.tags,
                "speed_rate": context.speed_rate,
                "pause_event": context.pause_event,
                "file_type": context.file_type,
                "publish_type": getattr(context, "publish_type", "video"),
                "cover_type": getattr(context, "cover_type", None),
                "cover_path": getattr(context, "cover_path", None),
                "scheduled_publish_time": st_str,
                "privacy_settings": getattr(context, "privacy_settings", None),
                "_diagnostic_context": {
                    "account_name": context.account_name,
                    "file_path": context.file_path,
                },
            }
            from src.domain.publish.location_settings import LocationPublishFields

            LocationPublishFields(
                poi_info=getattr(context, "poi_info", None) or "",
                wechat_empty_location_open_picker=getattr(
                    context, "wechat_empty_location_open_picker", None
                ),
            ).apply_to_plugin_metadata(metadata)

            _poi_for_resolve = (metadata.get("poi_info") or "").strip()
            if _poi_for_resolve:
                from src.domain.publish.location_settings import (
                    LocationPromotionPublishFields,
                    parse_location_short_name_from_storage,
                )

                if parse_location_short_name_from_storage(_poi_for_resolve):
                    try:
                        resolved_poi = (
                            await LocationPromotionPublishFields.resolve_poi_info_for_platform(
                                _poi_for_resolve, platform
                            )
                        )
                        if resolved_poi:
                            metadata["poi_info"] = resolved_poi
                    except Exception as _loc_err:
                        logger.warning(
                            "位置推广库解析失败（不阻断发布）: %s", _loc_err
                        )

            # 带货推广：优先处理含 cart_short_name（或旧键 yellow_cart_short_name）的 cart_info
            # 按简称查库，注入各平台链接/名称。cart_short_title 仅属购物车挂载数据，此处不参与查询。
            _cart_raw = getattr(context, "cart_info", None)
            _cart_str = str(_cart_raw).strip() if _cart_raw is not None else ""
            _cart_short_name = ""
            if _cart_str.startswith("{"):
                try:
                    import json as _json_exec
                    _d = _json_exec.loads(_cart_str)
                    # 新键优先，兼容旧键
                    _cart_short_name = (
                        _d.get("cart_short_name") or _d.get("yellow_cart_short_name") or ""
                    ).strip()
                except Exception:
                    pass
            if _cart_short_name:
                # 异步查询商品库，注入 cart_info 或 kuaishou_goods_name
                try:
                    from src.domain.publish.promotion_settings import CartPublishFields
                    _cart_fields = await CartPublishFields.from_short_name_and_platform(
                        _cart_short_name, platform
                    )
                    _cart_fields.apply_to_plugin_metadata(metadata)
                except Exception as _cart_err:
                    logger.warning("购物车商品查询失败（不阻断发布）: %s", _cart_err)
            elif _cart_str:
                # 纯文本链接或普通 JSON，直接写入 cart_info
                from src.domain.publish.promotion_settings import CartPublishFields
                CartPublishFields.from_platform_value(_cart_str, platform).apply_to_plugin_metadata(metadata)

            for _k in ("anchor_info", "micro_app_info"):
                _v = getattr(context, _k, None)
                if _v is not None and str(_v).strip():
                    metadata[_k] = str(_v).strip()

            # 音乐配置：解析 music_info JSON，注入 music_type/music_name/skip_select_music
            _music_raw = getattr(context, "music_info", None)
            if _music_raw and str(_music_raw).strip():
                try:
                    import json as _json_music
                    _music_dict = _json_music.loads(str(_music_raw).strip())
                    _music_type = (_music_dict.get("music_type") or "").strip()
                    _music_name = (_music_dict.get("music_name") or "").strip()
                    if _music_type == "random":
                        # 随机音乐：打开抽屉后随机取第一条
                        metadata["music_random"] = True
                        metadata["music_keyword"] = ""
                        metadata["music_name"] = ""
                    elif _music_type == "specific" and _music_name:
                        # 指定音乐：以音乐名称作为搜索关键字，再精确匹配
                        metadata["music_keyword"] = _music_name
                        metadata["music_name"] = _music_name
                except Exception:
                    pass

            result = await plugin.publish(
                context=context.page,  # 传入 Playwright Page 对象
                file_path=context.file_path,
                metadata=metadata
            )
            
            return result
            
        except Exception as e:
            logger.error(f"平台发布失败: {e}", exc_info=True)
            return PublishResult(
                success=False,
                error_message=str(e)
            )
    
    async def _publish_video_with_plugin(
        self,
        plugin,
        context: PublishContext
    ) -> PublishResult:
        """使用插件发布视频
        
        Args:
            plugin: 平台插件实例
            context: 发布上下文
            
        Returns:
            发布结果
        """
        try:
            # 调用插件的发布方法
            # 注意：插件的 publish_video 可能需要适配异步
            result = await plugin.publish_video(
                page=context.page,
                file_path=context.file_path,
                title=context.title,
                description=context.description,
                tags=context.tags,
                speed_rate=context.speed_rate,
                pause_event=context.pause_event
            )
            
            if result.get('success'):
                return PublishResult(
                    success=True,
                    publish_url=result.get('publish_url')
                )
            else:
                # 插件返回 'message' 字段，兼容读取
                error_msg = result.get('message') or result.get('error_message', '发布失败')
                logger.error(f"插件发布失败: {error_msg}")
                return PublishResult(
                    success=False,
                    error_message=error_msg
                )
                
        except Exception as e:
            return PublishResult(
                success=False,
                error_message=str(e)
            )
    
    async def _publish_image_with_plugin(
        self,
        plugin,
        context: PublishContext
    ) -> PublishResult:
        """使用插件发布图片
        
        Args:
            plugin: 平台插件实例
            context: 发布上下文
            
        Returns:
            发布结果
        """
        try:
            result = await plugin.publish_image(
                page=context.page,
                image_paths=[context.file_path],
                title=context.title,
                description=context.description,
                tags=context.tags
            )
            
            if result.get('success'):
                return PublishResult(
                    success=True,
                    publish_url=result.get('publish_url')
                )
            else:
                return PublishResult(
                    success=False,
                    error_message=result.get('error_message', '发布失败')
                )
                
        except Exception as e:
            return PublishResult(
                success=False,
                error_message=str(e)
            )
    
    async def execute_batch(
        self,
        tasks: List[Dict[str, Any]]
    ) -> List[PublishResult]:
        """批量执行发布任务
        
        Args:
            tasks: 任务列表，每个任务包含 account_name, platform, file_path 等
            
        Returns:
            发布结果列表
        """
        coroutines = [
            self.execute_single(
                account_name=task.get('account_name'),
                platform=task.get('platform'),
                file_path=task.get('file_path'),
                title=task.get('title', ''),
                description=task.get('description', ''),
                tags=task.get('tags'),
                file_type=task.get('file_type', 'video'),
                headless=task.get('headless', True),
                speed_rate=task.get('speed_rate', 1.0),
                scheduled_publish_time=task.get('scheduled_publish_time'),
                privacy_settings=task.get('privacy_settings'),
                cover_type=task.get('cover_type'),
                cover_path=task.get('cover_path'),
                close_browser_after=task.get('close_browser_after', True),
            )
            for task in tasks
        ]
        
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append(PublishResult(
                    success=False,
                    error_message=str(result)
                ))
            else:
                processed_results.append(result)
        
        return processed_results


class PublishExecutorFactory:
    """发布执行器工厂"""
    
    _instances: Dict[int, PublishExecutor] = {}
    
    @classmethod
    def get_executor(
        cls,
        user_id: int,
        data_storage=None,
        max_concurrent: int = 3
    ) -> PublishExecutor:
        """获取或创建发布执行器
        
        Args:
            user_id: 用户ID
            data_storage: 数据存储实例
            max_concurrent: 最大并发数
            
        Returns:
            发布执行器实例
        """
        if user_id not in cls._instances:
            cls._instances[user_id] = PublishExecutor(
                user_id=user_id,
                data_storage=data_storage,
                max_concurrent=max_concurrent
            )
        return cls._instances[user_id]
    
    @classmethod
    def clear_executor(cls, user_id: int):
        """清除指定用户的执行器"""
        if user_id in cls._instances:
            del cls._instances[user_id]
