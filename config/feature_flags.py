"""
功能开关配置
文件路径：config/feature_flags.py
功能：定义开源版与 Pro 版的功能开关，控制功能可用性
"""

from typing import Dict, Set
from functools import wraps
import os
import logging
import json
from pathlib import Path
import sys

logger = logging.getLogger(__name__)


# ============================================================
# 全局特性开关
# ============================================================

# 是否启用 v2.0 插件系统架构
# True: 优先使用 src/plugins/ 中的插件逻辑
# False: 强制使用旧版硬编码逻辑
USE_PLUGIN_SYSTEM = True


# ============================================================
# 功能开关定义
# ============================================================

class FeatureFlags:
    """功能开关管理器"""

    # 发行模式：OSS=开源版；PRO=闭源完整版；52POJIE=闭源离线特别版
    # 说明：这是“构建/分发维度”的能力开关，不等同于账号授权状态。
    _dist_mode: str | None = None
    _dist_mode_source: str | None = None

    @classmethod
    def _read_dist_mode_file(cls) -> str:
        """从 config/dist_mode.json 读取发行模式（用于打包产物在用户机器上运行时的默认值）。"""
        try:
            # 打包后（PyInstaller/Nuitka）源码模块位置与资源文件位置并不一致：
            # - dist_mode.json 作为“资源文件”会落在安装目录的 config/dist_mode.json
            # - feature_flags.py 可能位于打包的内部包体中，__file__ 推算会找不到 json
            # 因此优先通过 PathManager 取资源路径；失败再回退到与当前文件同目录。
            candidates: list[Path] = []

            # 1) 优先：统一资源路径（兼容 PyInstaller/Nuitka/开发环境）
            try:
                from src.infrastructure.common.path_manager import PathManager

                candidates.append(PathManager.get_resource_path("config/dist_mode.json"))
            except Exception:
                pass

            # 2) 兜底：基于可执行文件的相对路径（某些打包/启动方式下更稳）
            try:
                exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
                candidates.append(exe_dir / "config" / "dist_mode.json")
                candidates.append(exe_dir / "_internal" / "config" / "dist_mode.json")
            except Exception:
                pass

            # 3) 最后：与当前模块同目录（开发环境下通常可用）
            try:
                candidates.append(Path(__file__).resolve().parent / "dist_mode.json")
            except Exception:
                pass

            p = next((x for x in candidates if isinstance(x, Path) and x.exists()), None)
            if p is None:
                cls._dist_mode_source = "missing"
                return "OSS"

            # 兼容 UTF-8 BOM（部分构建/工具链会把 JSON 写成 UTF-8 with BOM，json.loads 会报 Unexpected UTF-8 BOM）
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            v = str(data.get("dist_mode", "")).strip().upper()
            if v in {"OSS", "PRO", "52POJIE"}:
                cls._dist_mode_source = str(p)
                return v
            cls._dist_mode_source = f"{p} (invalid value)"
            return "OSS"
        except Exception as e:
            cls._dist_mode_source = f"exception: {e}"
            return "OSS"

    @classmethod
    def get_dist_mode(cls) -> str:
        """获取发行模式（优先环境变量，其次 dist_mode.json）。"""
        if cls._dist_mode:
            return cls._dist_mode
        env = os.environ.get("APP_DIST_MODE", "").strip().upper()
        if env in {"OSS", "PRO", "52POJIE"}:
            cls._dist_mode = env
            cls._dist_mode_source = "env:APP_DIST_MODE"
        else:
            cls._dist_mode = cls._read_dist_mode_file()
        return cls._dist_mode

    @classmethod
    def refresh_dist_mode(cls) -> str:
        """刷新发行模式缓存（用于测试或运行中修改环境变量/文件后重新读取）。"""
        cls._dist_mode = None
        cls._dist_mode_source = None
        return cls.get_dist_mode()

    @classmethod
    def debug_dist_mode(cls) -> dict:
        """调试用：返回发行模式与来源（用于定位“安装后仍显示 OSS”问题）。"""
        mode = cls.get_dist_mode()
        return {"dist_mode": mode, "source": cls._dist_mode_source or ""}
    
    # 开源功能（Community Edition）- 默认启用
    COMMUNITY_FEATURES: Set[str] = {
        'douyin_login',              # 抖音账号登录
        'douyin_single_publish',     # 抖音单视频发布
        'basic_ui',                  # 基础 UI 框架
        'browser_manager',           # 浏览器管理
    }
    
    # Pro 功能（需要许可证）- 默认禁用
    PRO_FEATURES: Set[str] = {
        'batch_publish',             # 批量发布
        'scheduled_publish',         # 定时发布
        'kuaishou_platform',         # 快手平台
        # 'xiaohongshu_platform',      # 小红书平台
        'wechat_video_platform',     # 视频号平台
        'user_auth',                 # 用户认证
        'subscription',              # 订阅管理
        'material_library',          # 媒体库（视频/图片/文案）
        'commerce_promotion',        # 带货推广（购物车/团购）
        'data_center',               # 数据中心
        'interaction',               # 评论及私信
        'advanced_scheduler',        # 高级调度
        'checkpoint_resume',         # 断点续传
        'multi_account_batch',       # 多账号批量
    }
    
    # 开源平台列表
    OPEN_SOURCE_PLATFORMS: Set[str] = {'douyin'}
    
    # Pro 平台列表
    PRO_PLATFORMS: Set[str] = {'kuaishou', 'wechat_video'} # 'xiaohongshu'
    
    # 运行时状态
    _pro_licensed: bool = False
    _license_key: str = ""

    @classmethod
    def is_pro_build(cls) -> bool:
        """是否为 Pro 构建（闭源安装包）。"""
        return cls.get_dist_mode() in {"PRO", "52POJIE"}

    @classmethod
    def is_52pojie(cls) -> bool:
        """是否为 52POJIE 闭源离线特别版。"""
        return cls.get_dist_mode() == "52POJIE"

    @classmethod
    def is_feature_enabled(cls, feature: str) -> bool:
        """检查功能是否启用
        
        Args:
            feature: 功能名称
            
        Returns:
            True 如果功能可用
        """
        # 开源功能始终可用
        if feature in cls.COMMUNITY_FEATURES:
            return True
        
        # Pro 功能需要许可证
        if feature in cls.PRO_FEATURES:
            # Pro 构建：功能可用（具体权限由账号/订阅体系控制）
            if cls.is_pro_build():
                return True
            # OSS 构建：默认禁用 Pro 功能（保留许可证机制做扩展）
            return cls._pro_licensed
        
        # 未知功能默认禁用
        logger.warning(f"未知功能: {feature}")
        return False
    
    @classmethod
    def is_platform_available(cls, platform: str) -> bool:
        """检查平台是否可用
        
        Args:
            platform: 平台ID
            
        Returns:
            True 如果平台可用
        """
        if platform in cls.OPEN_SOURCE_PLATFORMS:
            return True
        
        if platform in cls.PRO_PLATFORMS:
            return cls.is_pro_build() or cls._pro_licensed
        
        return False
    
    @classmethod
    def get_available_platforms(cls) -> Set[str]:
        """获取当前可用的平台列表"""
        platforms = cls.OPEN_SOURCE_PLATFORMS.copy()
        if cls.is_pro_build() or cls._pro_licensed:
            platforms.update(cls.PRO_PLATFORMS)
        return platforms
    
    @classmethod
    def activate_pro(cls, license_key: str) -> bool:
        """激活 Pro 版本
        
        Args:
            license_key: 许可证密钥
            
        Returns:
            True 如果激活成功
        """
        # TODO: 实现许可证验证逻辑
        # 这里只是占位符，实际需要服务端验证
        if license_key and len(license_key) > 0:
            cls._pro_licensed = True
            cls._license_key = license_key
            logger.info("Pro 版本已激活")
            return True
        return False
    
    @classmethod
    def is_pro_licensed(cls) -> bool:
        """检查是否为 Pro 版本"""
        return cls.is_pro_build() or cls._pro_licensed
    
    @classmethod
    def get_edition_name(cls) -> str:
        """获取版本名称"""
        return "Pro Edition" if cls.is_pro_licensed() else "Community Edition"


# ============================================================
# 功能装饰器
# ============================================================

class FeatureNotAvailableError(Exception):
    """功能不可用异常"""
    
    def __init__(self, feature: str, message: str | None = None):
        self.feature = feature
        self.message = message or f"功能 '{feature}' 需要 Pro 版本"
        super().__init__(self.message)


def require_feature(feature: str):
    """功能要求装饰器
    
    用法:
        @require_feature('batch_publish')
        def my_pro_function():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not FeatureFlags.is_feature_enabled(feature):
                raise FeatureNotAvailableError(feature)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def require_pro(func):
    """Pro 版本要求装饰器
    
    用法:
        @require_pro
        def my_pro_function():
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not FeatureFlags.is_pro_licensed():
            raise FeatureNotAvailableError("pro", "此功能需要 Pro 版本")
        return func(*args, **kwargs)
    return wrapper


def require_platform(platform: str):
    """平台要求装饰器
    
    用法:
        @require_platform('kuaishou')
        def kuaishou_publish():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not FeatureFlags.is_platform_available(platform):
                raise FeatureNotAvailableError(
                    f"{platform}_platform",
                    f"平台 '{platform}' 需要 Pro 版本"
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================
# 便捷函数
# ============================================================

def is_feature_enabled(feature: str) -> bool:
    """检查功能是否启用（便捷函数）"""
    return FeatureFlags.is_feature_enabled(feature)


def is_platform_available(platform: str) -> bool:
    """检查平台是否可用（便捷函数）"""
    return FeatureFlags.is_platform_available(platform)


def is_pro() -> bool:
    """检查是否为 Pro 版本（便捷函数）"""
    return FeatureFlags.is_pro_licensed()


def get_available_platforms() -> Set[str]:
    """获取可用平台列表（便捷函数）"""
    return FeatureFlags.get_available_platforms()
