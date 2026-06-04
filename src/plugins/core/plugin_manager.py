# -*- coding: utf-8 -*-
"""
插件管理器 (v2.2 - 按需加载 + 全量可选)
文件路径：src/plugins/core/plugin_manager.py
功能：管理平台插件的加载与获取

- 默认按需加载：get_login_plugin/get_publish_plugin 首次访问某平台时才 import 并缓存。
- 环境变量 PLUGIN_EAGER_INIT=1 时恢复启动期全量静态导入（兼容旧行为/打包排查）。
- 打包时通过 _plugin_imports_for_packaging 显式引用所有插件模块，确保 Nuitka 能收集。
"""

import importlib
import logging
import os
from typing import Dict, Optional, List, Tuple, Callable, Any

from .interfaces.login_plugin import LoginPluginInterface
from .interfaces.publish_plugin import PublishPluginInterface

logger = logging.getLogger(__name__)

# 平台注册表：(platform_id, login_module, login_class, publish_module, publish_class)
# 仅用于按需加载时解析，不触发 import
PLUGIN_REGISTRY: List[Tuple[str, str, str, str, str]] = [
    ("douyin", "src.plugins.community.douyin.login_plugin", "DouyinLoginPlugin", "src.plugins.community.douyin.publish_plugin", "DouyinPublishPlugin"),
    ("kuaishou", "src.plugins.community.kuaishou.login_plugin", "KuaishouLoginPlugin", "src.plugins.community.kuaishou.publish_plugin", "KuaishouPublishPlugin"),
    ("wechat_video", "src.plugins.pro.wechat_video.login_plugin", "WechatVideoLoginPlugin", "src.plugins.pro.wechat_video.publish_plugin", "WechatVideoPublishPlugin"),
    # ("xiaohongshu", "src.plugins.pro.xiaohongshu.login_plugin", "XiaohongshuLoginPlugin", "src.plugins.pro.xiaohongshu.publish_plugin", "XiaohongshuPublishPlugin"),
    ("bilibili", "src.plugins.pro.bilibili.login_plugin", "BilibiliLoginPlugin", "src.plugins.pro.bilibili.publish_plugin", "BilibiliPublishPlugin"),
    ("weibo", "src.plugins.pro.weibo.login_plugin", "WeiboLoginPlugin", "src.plugins.pro.weibo.publish_plugin", "WeiboPublishPlugin"),
    ("toutiao", "src.plugins.pro.toutiao.login_plugin", "ToutiaoLoginPlugin", "src.plugins.pro.toutiao.publish_plugin", "ToutiaoPublishPlugin"),
    ("baijiahao", "src.plugins.pro.baijiahao.login_plugin", "BaijiahaoLoginPlugin", "src.plugins.pro.baijiahao.publish_plugin", "BaijiahaoPublishPlugin"),
    ("duoduoshipin", "src.plugins.pro.duoduoshipin.login_plugin", "DuoduoshipinLoginPlugin", "src.plugins.pro.duoduoshipin.publish_plugin", "DuoduoshipinPublishPlugin"),
    ("qiehao", "src.plugins.pro.qiehao.login_plugin", "QiehaoLoginPlugin", "src.plugins.pro.qiehao.publish_plugin", "QiehaoPublishPlugin"),
]


def _make_factory(module_path: str, class_name: str) -> Callable[[], Any]:
    """返回一个无参可调用对象，调用时 import 指定模块并实例化指定类。"""
    def factory() -> Any:
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)()
    return factory


class PluginManager:
    """
    插件管理器 - 默认按需加载，可选启动期全量初始化（PLUGIN_EAGER_INIT=1）
    """

    _login_plugins: Dict[str, LoginPluginInterface] = {}
    _publish_plugins: Dict[str, PublishPluginInterface] = {}
    _plugin_factories: Optional[Dict[str, Tuple[Callable[[], LoginPluginInterface], Callable[[], PublishPluginInterface]]]] = None
    _initialized = False

    @classmethod
    def _ensure_factories(cls) -> None:
        """确保 _plugin_factories 已从 PLUGIN_REGISTRY 构建（不触发任何插件 import）。"""
        if cls._plugin_factories is not None:
            return
        cls._plugin_factories = {}
        for platform_id, login_mod, login_cls, pub_mod, pub_cls in PLUGIN_REGISTRY:
            cls._plugin_factories[platform_id] = (
                _make_factory(login_mod, login_cls),
                _make_factory(pub_mod, pub_cls),
            )

    @classmethod
    def initialize(cls) -> None:
        """初始化插件系统。PLUGIN_EAGER_INIT=1 时全量静态导入；否则仅标记已初始化，按需加载。"""
        if cls._initialized:
            return
        if os.environ.get("PLUGIN_EAGER_INIT", "").strip().lower() in ("1", "true", "yes"):
            logger.info("正在初始化插件系统（静态导入模式，PLUGIN_EAGER_INIT=1）...")
            cls._register_all_plugins()
        else:
            cls._ensure_factories()
        cls._initialized = True
        if cls._login_plugins or cls._publish_plugins:
            logger.info(
                f"插件初始化完成. "
                f"登录插件: {list(cls._login_plugins.keys())}, "
                f"发布插件: {list(cls._publish_plugins.keys())}"
            )

    @classmethod
    def _register_all_plugins(cls):
        """静态注册所有已知的平台插件（Nuitka/PyInstaller 兼容）

        如需新增平台，请在此方法中添加对应的 import 和注册语句。
        """

        # ========================================
        # 社区插件 (community)
        # ========================================

        # --- 抖音 ---
        try:
            from src.plugins.community.douyin.login_plugin import DouyinLoginPlugin
            cls._login_plugins["douyin"] = DouyinLoginPlugin()
            logger.debug("已加载插件: DouyinLoginPlugin (douyin)")
        except Exception as e:
            logger.error(f"加载抖音登录插件失败: {e}", exc_info=True)

        try:
            from src.plugins.community.douyin.publish_plugin import DouyinPublishPlugin
            cls._publish_plugins["douyin"] = DouyinPublishPlugin()
            logger.debug("已加载插件: DouyinPublishPlugin (douyin)")
        except Exception as e:
            logger.error(f"加载抖音发布插件失败: {e}", exc_info=True)

        # --- 快手 ---
        try:
            from src.plugins.community.kuaishou.login_plugin import KuaishouLoginPlugin
            cls._login_plugins["kuaishou"] = KuaishouLoginPlugin()
            logger.debug("已加载插件: KuaishouLoginPlugin (kuaishou)")
        except Exception as e:
            logger.error(f"加载快手登录插件失败: {e}", exc_info=True)

        try:
            from src.plugins.community.kuaishou.publish_plugin import KuaishouPublishPlugin
            cls._publish_plugins["kuaishou"] = KuaishouPublishPlugin()
            logger.debug("已加载插件: KuaishouPublishPlugin (kuaishou)")
        except Exception as e:
            logger.error(f"加载快手发布插件失败: {e}", exc_info=True)

        # ========================================
        # 专业版插件 (pro)
        # ========================================

        # --- 视频号 ---
        try:
            from src.plugins.pro.wechat_video.login_plugin import WechatVideoLoginPlugin
            cls._login_plugins["wechat_video"] = WechatVideoLoginPlugin()
            logger.debug("已加载插件: WechatVideoLoginPlugin (wechat_video)")
        except Exception as e:
            logger.warning(f"加载视频号登录插件失败（可能未授权）: {e}")

        try:
            from src.plugins.pro.wechat_video.publish_plugin import WechatVideoPublishPlugin
            cls._publish_plugins["wechat_video"] = WechatVideoPublishPlugin()
            logger.debug("已加载插件: WechatVideoPublishPlugin (wechat_video)")
        except Exception as e:
            logger.warning(f"加载视频号发布插件失败（可能未授权）: {e}")

        # --- 小红书 ---
        # try:
        #     from src.plugins.pro.xiaohongshu.login_plugin import XiaohongshuLoginPlugin
        #     cls._login_plugins["xiaohongshu"] = XiaohongshuLoginPlugin()
        #     logger.debug("已加载插件: XiaohongshuLoginPlugin (xiaohongshu)")
        # except Exception as e:
        #     logger.warning(f"加载小红书登录插件失败（可能未授权）: {e}")

        # try:
        #     from src.plugins.pro.xiaohongshu.publish_plugin import XiaohongshuPublishPlugin
        #     cls._publish_plugins["xiaohongshu"] = XiaohongshuPublishPlugin()
        #     logger.debug("已加载插件: XiaohongshuPublishPlugin (xiaohongshu)")
        # except Exception as e:
        #     logger.warning(f"加载小红书发布插件失败（可能未授权）: {e}")

        # --- 哔哩哔哩 ---
        try:
            from src.plugins.pro.bilibili.login_plugin import BilibiliLoginPlugin
            cls._login_plugins["bilibili"] = BilibiliLoginPlugin()
            logger.debug("已加载插件: BilibiliLoginPlugin (bilibili)")
        except Exception as e:
            logger.warning(f"加载哔哩哔哩登录插件失败（可能未授权）: {e}")

        try:
            from src.plugins.pro.bilibili.publish_plugin import BilibiliPublishPlugin
            cls._publish_plugins["bilibili"] = BilibiliPublishPlugin()
            logger.debug("已加载插件: BilibiliPublishPlugin (bilibili)")
        except Exception as e:
            logger.warning(f"加载哔哩哔哩发布插件失败（可能未授权）: {e}")

        # --- 新浪微博 ---
        try:
            from src.plugins.pro.weibo.login_plugin import WeiboLoginPlugin
            cls._login_plugins["weibo"] = WeiboLoginPlugin()
            logger.debug("已加载插件: WeiboLoginPlugin (weibo)")
        except Exception as e:
            logger.warning(f"加载新浪微博登录插件失败（可能未授权）: {e}")

        try:
            from src.plugins.pro.weibo.publish_plugin import WeiboPublishPlugin
            cls._publish_plugins["weibo"] = WeiboPublishPlugin()
            logger.debug("已加载插件: WeiboPublishPlugin (weibo)")
        except Exception as e:
            logger.warning(f"加载新浪微博发布插件失败（可能未授权）: {e}")

        # --- 头条号 ---
        try:
            from src.plugins.pro.toutiao.login_plugin import ToutiaoLoginPlugin
            cls._login_plugins["toutiao"] = ToutiaoLoginPlugin()
            logger.debug("已加载插件: ToutiaoLoginPlugin (toutiao)")
        except Exception as e:
            logger.warning(f"加载头条号登录插件失败（可能未授权）: {e}")

        try:
            from src.plugins.pro.toutiao.publish_plugin import ToutiaoPublishPlugin
            cls._publish_plugins["toutiao"] = ToutiaoPublishPlugin()
            logger.debug("已加载插件: ToutiaoPublishPlugin (toutiao)")
        except Exception as e:
            logger.warning(f"加载头条号发布插件失败（可能未授权）: {e}")

        # --- 百家号 ---
        try:
            from src.plugins.pro.baijiahao.login_plugin import BaijiahaoLoginPlugin
            cls._login_plugins["baijiahao"] = BaijiahaoLoginPlugin()
            logger.debug("已加载插件: BaijiahaoLoginPlugin (baijiahao)")
        except Exception as e:
            logger.warning(f"加载百家号登录插件失败（可能未授权）: {e}")

        try:
            from src.plugins.pro.baijiahao.publish_plugin import BaijiahaoPublishPlugin
            cls._publish_plugins["baijiahao"] = BaijiahaoPublishPlugin()
            logger.debug("已加载插件: BaijiahaoPublishPlugin (baijiahao)")
        except Exception as e:
            logger.warning(f"加载百家号发布插件失败（可能未授权）: {e}")

        # --- 多多视频 ---
        try:
            from src.plugins.pro.duoduoshipin.login_plugin import DuoduoshipinLoginPlugin
            cls._login_plugins["duoduoshipin"] = DuoduoshipinLoginPlugin()
            logger.debug("已加载插件: DuoduoshipinLoginPlugin (duoduoshipin)")
        except Exception as e:
            logger.warning(f"加载多多视频登录插件失败（可能未授权）: {e}")

        try:
            from src.plugins.pro.duoduoshipin.publish_plugin import DuoduoshipinPublishPlugin
            cls._publish_plugins["duoduoshipin"] = DuoduoshipinPublishPlugin()
            logger.debug("已加载插件: DuoduoshipinPublishPlugin (duoduoshipin)")
        except Exception as e:
            logger.warning(f"加载多多视频发布插件失败（可能未授权）: {e}")

        # --- 企鹅号 ---
        try:
            from src.plugins.pro.qiehao.login_plugin import QiehaoLoginPlugin
            cls._login_plugins["qiehao"] = QiehaoLoginPlugin()
            logger.debug("已加载插件: QiehaoLoginPlugin (qiehao)")
        except Exception as e:
            logger.warning(f"加载企鹅号登录插件失败（可能未授权）: {e}")

        try:
            from src.plugins.pro.qiehao.publish_plugin import QiehaoPublishPlugin
            cls._publish_plugins["qiehao"] = QiehaoPublishPlugin()
            logger.debug("已加载插件: QiehaoPublishPlugin (qiehao)")
        except Exception as e:
            logger.warning(f"加载企鹅号发布插件失败（可能未授权）: {e}")

    @classmethod
    def get_login_plugin(cls, platform_id: str) -> Optional[LoginPluginInterface]:
        """获取登录插件；首次访问该平台时按需 import 并缓存。"""
        cls.initialize()
        cls._ensure_factories()
        if platform_id not in cls._login_plugins and cls._plugin_factories and platform_id in cls._plugin_factories:
            try:
                login_factory, _ = cls._plugin_factories[platform_id]
                cls._login_plugins[platform_id] = login_factory()
            except Exception as e:
                logger.warning("按需加载登录插件 %s 失败: %s", platform_id, e)
        return cls._login_plugins.get(platform_id)

    @classmethod
    def get_publish_plugin(cls, platform_id: str) -> Optional[PublishPluginInterface]:
        """获取发布插件；首次访问该平台时按需 import 并缓存。"""
        cls.initialize()
        cls._ensure_factories()
        if platform_id not in cls._publish_plugins and cls._plugin_factories and platform_id in cls._plugin_factories:
            try:
                _, publish_factory = cls._plugin_factories[platform_id]
                cls._publish_plugins[platform_id] = publish_factory()
            except Exception as e:
                logger.warning("按需加载发布插件 %s 失败: %s", platform_id, e)
        return cls._publish_plugins.get(platform_id)

    @classmethod
    def get_available_platforms(cls) -> List[str]:
        """获取所有可用平台ID列表（不触发任何插件 import）。"""
        cls.initialize()
        cls._ensure_factories()
        if cls._plugin_factories:
            return sorted(cls._plugin_factories.keys())
        return sorted(cls._login_plugins.keys())
