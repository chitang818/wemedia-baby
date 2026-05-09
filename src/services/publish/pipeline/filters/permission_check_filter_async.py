"""
权限检查过滤器（异步版本）
文件路径：src/business/publish_pipeline/filters/permission_check_filter_async.py
功能：检查用户发布权限（异步），含 Pro 平台权限校验。
"""

import time
from typing import Optional, Tuple, Any
from src.infrastructure.common.pipeline.base_filter import BaseFilter, PublishContext
from src.services.auth.current_user_service import CurrentUserService
from src.utils.pro_platforms import is_pro_platform
import logging

logger = logging.getLogger(__name__)

# publish_check 结果短时缓存：key=(token, platform, is_pro) → (allowed, expire_ts)
# 仅缓存 allowed=True 的结果，拒绝结果不缓存（确保封禁/降权立即生效）
_PUBLISH_CHECK_CACHE: dict = {}
_PUBLISH_CHECK_CACHE_TTL = 60  # 秒
_CACHE_MAX_SIZE = 200
_LAST_CLEANUP = 0.0
_CLEANUP_INTERVAL = 300  # 每 5 分钟全量清理一次


def _maybe_cleanup_cache() -> None:
    """定期清理过期条目，防止内存无限增长。"""
    global _LAST_CLEANUP
    now = time.monotonic()
    if now - _LAST_CLEANUP < _CLEANUP_INTERVAL:
        return
    _LAST_CLEANUP = now
    expired_keys = [k for k, (_, exp) in _PUBLISH_CHECK_CACHE.items() if now > exp]
    for k in expired_keys:
        _PUBLISH_CHECK_CACHE.pop(k, None)


def _evict_oldest_if_full() -> None:
    """超出上限时淘汰最早过期的条目。"""
    while len(_PUBLISH_CHECK_CACHE) >= _CACHE_MAX_SIZE:
        oldest_key = min(_PUBLISH_CHECK_CACHE, key=lambda k: _PUBLISH_CHECK_CACHE[k][1])
        _PUBLISH_CHECK_CACHE.pop(oldest_key, None)


def _get_cached_publish_check(token: str, platform: str, is_pro: bool) -> Optional[bool]:
    """返回缓存的 allowed 值，未命中或已过期返回 None。"""
    _maybe_cleanup_cache()
    key = (token, platform, is_pro)
    entry = _PUBLISH_CHECK_CACHE.get(key)
    if entry is None:
        return None
    allowed, exp = entry
    if time.monotonic() > exp:
        _PUBLISH_CHECK_CACHE.pop(key, None)
        return None
    return allowed


def _set_publish_check_cache(token: str, platform: str, is_pro: bool, allowed: bool) -> None:
    """写入缓存，仅缓存 allowed=True 的结果。"""
    if not allowed:
        return
    _evict_oldest_if_full()
    key = (token, platform, is_pro)
    _PUBLISH_CHECK_CACHE[key] = (allowed, time.monotonic() + _PUBLISH_CHECK_CACHE_TTL)


class PermissionCheckFilterAsync(BaseFilter):
    """权限检查过滤器（异步版本）"""
    
    def __init__(self, permission_controller: Optional[Any] = None):
        super().__init__()
        self.permission_controller = permission_controller
    
    async def process(self, context: PublishContext) -> bool:
        """只校验当前登录的媒小宝账号是否有发布权限；任务存在本地，不校验任务由哪个账号创建。"""
        try:
            # 开源/社区版：若未启用订阅能力或闭源控制器缺失，则跳过会员/云端校验，避免因缺失闭源代码导致崩溃。
            try:
                from config.feature_flags import FeatureFlags
                if not FeatureFlags.is_feature_enabled("subscription"):
                    return True
            except Exception:
                # 若 FeatureFlags 不可用，保守放行（避免阻断开源版运行）
                return True

            if self.permission_controller is None:
                return True

            curr = CurrentUserService()
            if not curr.is_logged_in():
                self.set_error("发布需要先登录")
                logger.warning("发布被拒绝（未登录）")
                return False
            # 权限与额度均按当前登录用户校验，不校验 context.user_id 与当前用户是否一致
            current_user_id = curr.get_user_id()
            platform = getattr(context, "platform", "") or ""
            # Pro 平台：校验当前用户 Pro 权限
            if is_pro_platform(platform):
                if not self.permission_controller.check_pro_permission(current_user_id):
                    self.set_error("需要 Pro 会员，请升级/续费")
                    logger.warning("Pro 平台发布被拒绝: user_id=%s, platform=%s", current_user_id, platform)
                    return False
            # 检查当前用户订阅状态
            if not await self.permission_controller.check_publish_permission(current_user_id):
                self.set_error("用户无发布权限，请检查订阅状态")
                return False
            # 检查当前用户试用次数
            if not await self.permission_controller.check_trial_count(current_user_id):
                self.set_error("试用次数已用完，请购买订阅")
                return False
            # 日发布数额度按当前用户校验
            daily_max = CurrentUserService().get_daily_max_publish_count()
            if daily_max is not None and daily_max > 0:
                from src.infrastructure.common.di.service_locator import ServiceLocator
                from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
                repo = ServiceLocator().get(PublishRecordRepositoryAsync)
                if repo:
                    today_count = await repo.count_today_success(current_user_id)
                    if today_count >= daily_max:
                        self.set_error(
                            f"今日发布数量已达上限（{daily_max}），请明日再试或升级会员。"
                        )
                        logger.warning(
                            "日发布数超限: user_id=%s, today_count=%s, max=%s",
                            current_user_id, today_count, daily_max,
                        )
                        return False
            # 发布前服务端校验（当前用户 token），带 60 秒短时缓存减少云函数调用次数
            from src.services.auth.auth_config import is_cloud_auth_enabled
            token = curr.get_token()
            if is_cloud_auth_enabled() and token:
                _is_pro = is_pro_platform(platform)
                cached = _get_cached_publish_check(token, platform, _is_pro)
                if cached is True:
                    logger.debug("publish_check 命中缓存（allowed）: platform=%s", platform)
                else:
                    from src.services.auth import auth_api_client
                    check_result = await auth_api_client.publish_check(token, platform, _is_pro)
                    if check_result.get("success"):
                        if not check_result.get("allowed"):
                            reason = check_result.get("reason") or "未通过服务端校验"
                            code = check_result.get("code")
                            if code == "SESSION_EVICTED" or "其他设备" in (reason or ""):
                                CurrentUserService().clear_user()
                                try:
                                    from src.infrastructure.common.di.service_locator import ServiceLocator
                                    from src.infrastructure.common.event.event_bus import EventBus
                                    from src.infrastructure.common.event.events import SessionEvictedEvent
                                    event_bus = ServiceLocator().get(EventBus)
                                    if event_bus:
                                        event_bus.publish_sync(SessionEvictedEvent(reason=reason))
                                except Exception as e:
                                    logger.debug("发布 SessionEvictedEvent 失败: %s", e)
                            self.set_error(reason)
                            logger.warning("发布前服务端校验未通过: user_id=%s, platform=%s, reason=%s", current_user_id, platform, reason)
                            return False
                        # 服务端放行，写入缓存
                        _set_publish_check_cache(token, platform, _is_pro, True)
                    else:
                        # 云端不可达降级放行，但本地过期账号仍拒绝
                        if curr._is_expired:
                            self.set_error("账号已过期，且无法连接授权服务进行验证，请重新登录")
                            logger.warning("降级校验：账号已过期，拒绝发布: user_id=%s", current_user_id)
                            return False
                        logger.warning("发布前服务端校验请求失败，降级放行: %s", check_result.get("reason", ""))
            logger.info("权限检查通过: current_user_id=%s, platform=%s", current_user_id, platform)
            return True
        except Exception as e:
            self.set_error(f"权限检查失败: {str(e)}")
            logger.error(self.get_error(), exc_info=True)
            return False

