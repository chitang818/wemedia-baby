"""
Tortoise ORM 模型包
功能：定义所有数据表对应的 ORM 模型类
"""

# 导出所有模型，便于 Tortoise.init 扫描
from src.infrastructure.storage.orm_models.user import User
from src.infrastructure.storage.orm_models.subscription import Subscription
from src.infrastructure.storage.orm_models.platform_account import PlatformAccount
from src.infrastructure.storage.orm_models.account_group import AccountGroup
from src.infrastructure.storage.orm_models.account_tag import AccountTag
from src.infrastructure.storage.orm_models.publish_record import PublishRecord
from src.infrastructure.storage.orm_models.login_log import LoginLog
from src.infrastructure.storage.orm_models.batch_task import BatchTask
from src.infrastructure.storage.orm_models.batch_task_execution import BatchTaskExecution
from src.infrastructure.storage.orm_models.batch_task_checkpoint import BatchTaskCheckpoint
from src.infrastructure.storage.orm_models.copywriting_item import CopywritingItem
from src.infrastructure.storage.orm_models.cart_promotion_item import CartPromotionItem
from src.infrastructure.storage.orm_models.location_promotion_item import (
    LocationPromotionItem,
)
from src.infrastructure.storage.orm_models.random_copywriting import (
    RandomCopywritingCategory,
    RandomCopywritingItem,
)

__all__ = [
    "User",
    "Subscription",
    "PlatformAccount",
    "AccountGroup",
    "AccountTag",
    "PublishRecord",
    "LoginLog",
    "BatchTask",
    "BatchTaskExecution",
    "BatchTaskCheckpoint",
    "CopywritingItem",
    "CartPromotionItem",
    "LocationPromotionItem",
    "RandomCopywritingCategory",
    "RandomCopywritingItem",
]
