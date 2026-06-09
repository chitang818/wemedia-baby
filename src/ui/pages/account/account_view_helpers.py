# -*- coding: utf-8 -*-
"""
账号页辅助函数
文件路径：src/ui/pages/account/account_view_helpers.py
功能：从 account view 抽出的「等待页面稳定并提取昵称」等逻辑，供 view 调用
"""
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)

# 各平台 login_plugin 的导入路径映射
_PLATFORM_LOGIN_PLUGIN_MAP = {
    "douyin": "src.plugins.community.douyin.login_plugin.DouyinLoginPlugin",
    "kuaishou": "src.plugins.community.kuaishou.login_plugin.KuaishouLoginPlugin",
    "wechat_video": "src.plugins.pro.wechat_video.login_plugin.WechatVideoLoginPlugin",
    "xiaohongshu": "src.plugins.pro.xiaohongshu.login_plugin.XiaohongshuLoginPlugin",
    "bilibili": "src.plugins.pro.bilibili.login_plugin.BilibiliLoginPlugin",
    "toutiao": "src.plugins.pro.toutiao.login_plugin.ToutiaoLoginPlugin",
    "weibo": "src.plugins.pro.weibo.login_plugin.WeiboLoginPlugin",
}


async def wait_page_networkidle_and_get_nickname(page: Any, platform: str) -> Optional[str]:
    """等待页面 networkidle 后按平台插件提取昵称（仅接受 page 的旧接口，供 _batch_sync_nicknames 使用）。

    注意：主流程的昵称提取由 PatchrightBrowserService 内的静默更新任务统一处理，
    此函数仅供深度同步昵称（Headless 批量提取）场景调用。

    Args:
        page: Playwright Page 实例
        platform: 平台标识，如 'douyin'

    Returns:
        昵称字符串，失败时返回 None
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception as e:
        logger.warning("等待页面 networkidle 超时或异常: %s", e)

    if platform == "douyin":
        # 抖音旧插件保持兼容
        try:
            from src.infrastructure.plugins.builtin_plugins.douyin_plugin import DouyinPlugin
            plugin = DouyinPlugin()
            await plugin.initialize()
            return await plugin.get_nickname(page)
        except Exception as e:
            logger.warning("抖音旧插件提取昵称失败，尝试新插件: %s", e)

    # 通用路径：通过 context 调用各平台 login_plugin.extract_user_info
    return await extract_nickname_via_login_plugin(page.context, platform)


async def extract_nickname_via_login_plugin(context: Any, platform: str) -> Optional[str]:
    """通过各平台 login_plugin 的 extract_user_info 提取昵称。

    适用于已有 Patchright browser context 的场景（主流程由 PatchrightBrowserService 处理，
    此函数供辅助场景调用）。

    Args:
        context: Playwright BrowserContext 实例
        platform: 平台标识，如 'kuaishou'

    Returns:
        昵称字符串，失败或未支持的平台返回 None
    """
    plugin_path = _PLATFORM_LOGIN_PLUGIN_MAP.get(platform)
    if not plugin_path:
        logger.debug("平台 %s 暂不支持自动提取昵称", platform)
        return None

    try:
        module_path, class_name = plugin_path.rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        plugin_cls = getattr(module, class_name)
        plugin = plugin_cls()
        result = await plugin.extract_user_info(context)
        nickname = getattr(result, "nickname", None)
        if nickname:
            logger.info("平台 %s 自动提取昵称成功: %s", platform, nickname)
        return nickname
    except ImportError:
        logger.debug("平台 %s 的 login_plugin 不可用（可能为 Pro 功能）", platform)
        return None
    except Exception as e:
        logger.warning("平台 %s 提取昵称失败: %s", platform, e)
        return None
