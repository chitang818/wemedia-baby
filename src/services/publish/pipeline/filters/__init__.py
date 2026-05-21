"""
发布管道过滤器模块
"""

# 异步版本 (新架构)
from .permission_check_filter_async import PermissionCheckFilterAsync
from .media_validate_filter_async import MediaValidateFilterAsync
from .account_load_filter_async import AccountLoadFilterAsync
from .record_save_filter_async import RecordSaveFilterAsync

# PlatformPublishFilterAsync 依赖已废弃的 src.platforms，当前 main 流水线使用 PublishExecutionFilter 代替；可选导入避免启动失败
PlatformPublishFilterAsync = None  # type: ignore[misc, assignment]

# 兼容性别名
PermissionCheckFilter = PermissionCheckFilterAsync
MediaValidateFilter = MediaValidateFilterAsync
AccountLoadFilter = AccountLoadFilterAsync
PlatformPublishFilter = PlatformPublishFilterAsync if PlatformPublishFilterAsync is not None else None
RecordSaveFilter = RecordSaveFilterAsync

__all__ = [
    'PermissionCheckFilterAsync',
    'MediaValidateFilterAsync',
    'AccountLoadFilterAsync',
    'PlatformPublishFilterAsync',
    'RecordSaveFilterAsync',
    # 兼容性别名
    'PermissionCheckFilter',
    'MediaValidateFilter',
    'AccountLoadFilter',
    'PlatformPublishFilter',
    'RecordSaveFilter',
]
