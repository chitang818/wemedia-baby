# 配置模块初始化
# config/__init__.py

from .feature_flags import (
    FeatureFlags,
    FeatureNotAvailableError,
    require_feature,
    require_pro,
    require_platform,
    is_feature_enabled,
    is_platform_available,
    is_pro,
    get_available_platforms
)

__all__ = [
    'FeatureFlags',
    'FeatureNotAvailableError',
    'require_feature',
    'require_pro',
    'require_platform',
    'is_feature_enabled',
    'is_platform_available',
    'is_pro',
    'get_available_platforms'
]
