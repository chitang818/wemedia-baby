"""
页面工厂 - 按需懒加载页面类，加快主窗口构建与首屏显示
"""
import sys
import logging
from typing import Dict, Type, Optional, Tuple
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

# 页面名 -> (模块路径, 类名)，首次 create_page 时再导入
_REGISTRY: Dict[str, Tuple[str, str]] = {
    "workspace_page": ("src.ui.pages.workspace_page", "WorkspacePage"),
    "account_page": ("src.ui.pages.account", "AccountPage"),
    "account_group_page": ("src.ui.pages.account_group", "AccountGroupPage"),
    "account_tag_page": ("src.ui.pages.account_tag", "AccountTagPage"),
    "publish_list_page": ("src.ui.pages.publish.publish_list_page", "PublishListPage"),
    "publish_records_page": ("src.ui.pages.publish", "PublishRecordsPage"),
    "publish_recycle_bin_page": (
        "src.ui.pages.publish.publish_recycle_bin_page",
        "PublishRecycleBinPage",
    ),
    "single_task_creation_page": (
        "src.ui.pages.publish.single_task_creation_page",
        "SingleTaskCreationPage",
    ),
    "image_single_task_creation_page": (
        "src.ui.pages.publish.image_single_task_creation_page",
        "ImageSingleTaskCreationPage",
    ),
    "settings_page": ("src.ui.pages.settings_page", "SettingsPage"),
    "video_library_page": ("src.ui.pages.material.video_library_page", "VideoLibraryPage"),
    "image_library_page": ("src.ui.pages.material.image_library_page", "ImageLibraryPage"),
    "copywriting_library_page": ("src.ui.pages.material.copywriting_library_page", "CopywritingLibraryPage"),
    "cart_promotion_page": ("src.ui.pages.material.cart_promotion_page", "CartPromotionPage"),
    "group_buy_promotion_page": ("src.ui.pages.material.group_buy_promotion_page", "GroupBuyPromotionPage"),
    "random_copywriting_page": ("src.ui.pages.material.random_copywriting_page", "RandomCopywritingPage"),
}


def _register_optional_pages() -> None:
    """注册可选页面（Pro/个人中心等），仅写入 registry 不触发导入，首次打开该页时再加载"""
    optional = [
        ("batch_task_creation_page", "src.pro_features.batch.pages.batch_task_creation_page", "BatchTaskCreationPage"),
        (
            "image_batch_task_creation_page",
            "src.pro_features.batch.pages.image_batch_task_creation_page",
            "ImageBatchTaskCreationPage",
        ),
        ("data_center_page", "src.pro_features.data_center.pages.data_center_page", "DataCenterPage"),
        ("comment_page", "src.pro_features.interaction.pages.comment_page", "CommentPage"),
        ("private_message_page", "src.pro_features.interaction.pages.private_message_page", "PrivateMessagePage"),
        ("personal_center_page", "src.ui.pages.subscription_page", "PersonalCenterPage"),
    ]
    for name, mod_path, class_name in optional:
        if name not in _REGISTRY:
            _REGISTRY[name] = (mod_path, class_name)


class PageFactory:
    """页面工厂 - 懒加载：仅在实际切换到此页面时导入并实例化"""

    def __init__(self):
        _register_optional_pages()
        self._registry: Dict[str, Tuple[str, str]] = dict(_REGISTRY)

    def _get_page_class(self, page_name: str) -> Optional[Type[QWidget]]:
        """按需导入并返回页面类"""
        if page_name not in self._registry:
            return None
        mod_path, class_name = self._registry[page_name]
        try:
            import time
            from src.utils.startup_profiler import is_page_load_profiler_enabled

            t0 = time.perf_counter() if is_page_load_profiler_enabled() else 0.0
            mod = __import__(mod_path, fromlist=[class_name])
            page_class = getattr(mod, class_name)
            if is_page_load_profiler_enabled():
                logging.getLogger("ui.perf").info(
                    "[页面耗时] import_page_class %s: %.0f ms",
                    page_name,
                    (time.perf_counter() - t0) * 1000,
                )
            return page_class
        except (ImportError, AttributeError) as e:
            logger.error("PageFactory: 导入页面失败 [%s] %s.%s: %s", page_name, mod_path, class_name, e)
            # 打包环境下弹窗提示用户，避免"点击无反应"的困惑
            if getattr(sys, 'frozen', False):
                try:
                    from src.ui.utils.fluent_dialogs import show_warning
                    show_warning(
                        None, "页面加载失败",
                        f"页面 [{page_name}] 加载失败。\n\n"
                        f"模块: {mod_path}.{class_name}\n"
                        f"错误: {e}\n\n"
                        f"请联系开发者或重新安装。"
                    )
                except Exception:
                    pass
            return None

    def create_page(self, page_name: str, parent: Optional[QWidget] = None) -> Optional[QWidget]:
        """创建页面实例（首次访问该页面时才导入对应模块）"""
        if page_name not in self._registry:
            logger.error("PageFactory: 未找到页面定义 [%s]", page_name)
            return None
        page_class = self._get_page_class(page_name)
        if not page_class:
            return None
        try:
            import time
            from src.utils.startup_profiler import is_page_load_profiler_enabled

            t0 = time.perf_counter() if is_page_load_profiler_enabled() else 0.0
            page_instance = page_class(parent)
            page_instance.setObjectName(page_name)
            if is_page_load_profiler_enabled():
                logging.getLogger("ui.perf").info(
                    "[页面耗时] instantiate_page %s: %.0f ms",
                    page_name,
                    (time.perf_counter() - t0) * 1000,
                )
            return page_instance
        except Exception as e:
            logger.error("PageFactory: 实例化页面失败 [%s]: %s", page_name, e, exc_info=True)
            return None

    def get_all_page_names(self) -> list:
        """返回已注册的页面名称列表"""
        return list(self._registry.keys())
