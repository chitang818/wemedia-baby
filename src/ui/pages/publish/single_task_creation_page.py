"""
单条发布任务创建页面（开源版）：单个视频或单个图文。
文件路径：src/ui/pages/publish/single_task_creation_page.py

说明：本页仅负责「创建发布任务」并写入发布列表，不在此执行实际上传。
      任务在「发布管理 → 发布列表」中点击发布按钮后才会执行。
功能：通过 media_mode 区分视频与图文；图文支持多图路径（英文逗号拼接，与抖音上传一致）。
"""

from typing import Optional, List, Literal, Dict, Any, Tuple, Set
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFileDialog, QComboBox, QTextEdit, QLineEdit,
    QFrame, QScrollArea, QButtonGroup, QDialog, QStackedWidget,
    QSizePolicy,
)
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtCore import (
    Qt,
    Signal,
    QDate,
    QTime,
    QDateTime,
    QEasingCurve,
    QPropertyAnimation,
    QUrl,
)
import logging
import os
import asyncio

from qfluentwidgets import (
    CardWidget, SubtitleLabel, BodyLabel, PrimaryPushButton,
    PushButton, FluentIcon, IconWidget, LineEdit, TextEdit,
    ComboBox, ProgressRing, InfoBar, InfoBarPosition,
    TimePicker, CheckBox, SmoothScrollArea,
    ImageLabel, RadioButton, StateToolTip, SwitchButton,
    isDarkTheme,
)
FLUENT_WIDGETS_AVAILABLE = True

# 表单行：标签列宽、控件间距（核心配置卡封面行等与更多发布设置视觉对齐）
_SETTINGS_LABEL_WIDTH = 72
_SETTINGS_ROW_GAP = 14
_SETTINGS_H_GAP = 10

from src.ui.components.fast_calendar_picker import create_fast_calendar_picker
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip
from src.ui.utils.task_tracking import TrackedTaskMixin

from ..base_page import BasePage
from .single_task_creation_controller import SingleTaskCreationController
from .single_task_creation_actions import add_or_update_publish_record, normalize_publish_record_id
from .single_more_publish_settings import MorePublishSettingsCard
from src.domain.publish.work_description import (
    normalize_topics_for_paste,
    parse_topic_list,
)
from src.ui.publish.work_description.work_description_edit_controller import WorkDescriptionEditController
from src.utils.date_utils import format_schedule_time_st_str
from qasync import asyncSlot

from src.ui.dialogs.file_select_dialog import (
    get_last_video_import_directory,
    save_last_video_import_directory_from_path,
)
from src.services.copywriting.copywriting_match_service import CopywritingMatchService, CopywritingMatchMode
from src.infrastructure.storage.repositories.random_copywriting_repository import RandomCopywritingRepository
logger = logging.getLogger(__name__)

# 封面类型下拉 userData
_COVER_TYPE_FIRST_FRAME = "first_frame"
_COVER_TYPE_LOCAL = "local"
COVER_TYPE_COMBO_WIDTH = 120

# 未选发布账号/组时的提示（默认进入页面、清空表单）
_ACCOUNT_LABEL_PLACEHOLDER = "请选择发布对象"

# 单条任务创建页 UI 常量
TITLE_MAX_LENGTH = 30
BUTTON_FIXED_WIDTH = 140
# 定时发布最早可选时间：相对当前时刻延后（秒），与校验逻辑一致
SCHEDULE_MIN_LEAD_SECS = 9000  # 2.5 小时
# TimePicker 无秒时库内默认每列 120px；改为 80px（库 showSeconds=True 时的内置窄宽度），
# 弹窗渲染与高亮条在此宽度下完全兼容，无需猴子补丁。
SCHEDULE_TIME_PICKER_COL_WIDTH = 80

def _single_publish_root() -> dict:
    from src.infrastructure.common.config.config_center import get_registered_config_center
    from src.infrastructure.common.config.app_config_keys import KEY_SINGLE_PUBLISH
    from src.infrastructure.common.config.app_config_merge import read_app_config_from_disk_sync

    cc = get_registered_config_center()
    if cc is not None:
        sp = cc.get_app_config().get(KEY_SINGLE_PUBLISH)
        if isinstance(sp, dict):
            return sp
        return {}
    root = read_app_config_from_disk_sync()
    sp = root.get(KEY_SINGLE_PUBLISH)
    return sp if isinstance(sp, dict) else {}


def _schedule_persist_single_publish_keys(partial: Dict[str, Any]) -> None:
    """经配置中心合并写入 ``single_publish``（无中心时回退磁盘），供开关与勾选即时落盘。"""
    from src.ui.utils.async_helper import run_async_from_ui
    from src.infrastructure.common.config.app_config_merge import persist_single_publish_partial_async

    async def _save() -> None:
        try:
            await persist_single_publish_partial_async(partial)
        except Exception as e:
            logger.warning("写入 single_publish 配置失败: %s", e, exc_info=True)

    try:
        run_async_from_ui(_save)
    except Exception as e:
        logger.warning("调度 single_publish 配置写入失败: %s", e)


def load_persisted_single_auto_match_video_library() -> bool:
    """读取单视频发布页「视频库自动匹配」开关；无记录时默认 False。"""
    from src.infrastructure.common.config.app_config_keys import SINGLE_AUTO_MATCH_VIDEO_LIBRARY

    sp = _single_publish_root()
    if SINGLE_AUTO_MATCH_VIDEO_LIBRARY not in sp:
        return False
    try:
        v = sp.get(SINGLE_AUTO_MATCH_VIDEO_LIBRARY)
        return bool(v) and str(v).lower() not in ("0", "false", "")
    except Exception:
        logger.debug("读取单视频自动匹配视频库失败", exc_info=True)
        return False


def save_persisted_single_auto_match_video_library(checked: bool) -> None:
    """保存单视频发布页「视频库自动匹配」开关（配置中心 + app_config.json）。"""
    from src.infrastructure.common.config.app_config_keys import SINGLE_AUTO_MATCH_VIDEO_LIBRARY

    _schedule_persist_single_publish_keys({SINGLE_AUTO_MATCH_VIDEO_LIBRARY: checked})


def load_persisted_single_auto_match_copywriting() -> bool:
    """读取单视频页「文案库自动匹配」开关；无记录时默认 False。"""
    from src.infrastructure.common.config.app_config_keys import SINGLE_AUTO_MATCH_COPYWRITING

    sp = _single_publish_root()
    if SINGLE_AUTO_MATCH_COPYWRITING not in sp:
        return False
    try:
        v = sp.get(SINGLE_AUTO_MATCH_COPYWRITING)
        return bool(v) and str(v).lower() not in ("0", "false", "")
    except Exception:
        logger.debug("读取单视频文案库自动匹配失败", exc_info=True)
        return False


def save_persisted_single_auto_match_copywriting(checked: bool) -> None:
    """保存单视频页「文案库自动匹配」开关（配置中心 + app_config.json）。"""
    from src.infrastructure.common.config.app_config_keys import SINGLE_AUTO_MATCH_COPYWRITING

    _schedule_persist_single_publish_keys({SINGLE_AUTO_MATCH_COPYWRITING: checked})


def load_persisted_single_copywriting_match_mode() -> str:
    """读取单任务页文案匹配模式；默认 standard。"""
    from src.infrastructure.common.config.app_config_keys import SINGLE_COPYWRITING_MATCH_MODE

    sp = _single_publish_root()
    return str(sp.get(SINGLE_COPYWRITING_MATCH_MODE) or CopywritingMatchMode.STANDARD)


def save_persisted_single_copywriting_match_mode(mode: str) -> None:
    """保存单任务页文案匹配模式。"""
    from src.infrastructure.common.config.app_config_keys import SINGLE_COPYWRITING_MATCH_MODE

    _schedule_persist_single_publish_keys({SINGLE_COPYWRITING_MATCH_MODE: mode})


def load_persisted_single_copywriting_random_category() -> Optional[int]:
    """读取单任务页随机匹配分类 ID。"""
    from src.infrastructure.common.config.app_config_keys import SINGLE_COPYWRITING_RANDOM_CATEGORY

    sp = _single_publish_root()
    v = sp.get(SINGLE_COPYWRITING_RANDOM_CATEGORY)
    try:
        return int(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def save_persisted_single_copywriting_random_category(category_id: Optional[int]) -> None:
    """保存单任务页随机匹配分类 ID。"""
    from src.infrastructure.common.config.app_config_keys import SINGLE_COPYWRITING_RANDOM_CATEGORY

    _schedule_persist_single_publish_keys({SINGLE_COPYWRITING_RANDOM_CATEGORY: category_id})


def _theme_colors():
    """返回当前主题下各 UI 元素的颜色字典"""
    dark = isDarkTheme()
    return {
        "preview_bg": "#2B2B2B" if dark else "#f8f8f8",
        "preview_border": "#555" if dark else "#ddd",
        "preview_text": "#AAA" if dark else "#888",
        "entry_bg": "#2B2B2B" if dark else "white",
        "entry_border": "#555" if dark else "#e5e5e5",
        "entry_hover_border": "#888" if dark else "#ccc",
        "separator": "#444" if dark else "#f2f2f2",
        "hint_text": "#AAA" if dark else "#888",
        "count_text": "#777" if dark else "#ccc",
    }


_FOLDER_MARKER_PREFIX = "__FOLDER__:"


def _split_comma_paths(file_path: str) -> List[str]:
    """将发布记录中的 file_path 按英文逗号拆成路径列表（与抖音图文上传解析一致）。
    
    自动过滤文件夹来源标记（__FOLDER__: 开头的条目），只返回真实图片路径。
    """
    return [
        p.strip()
        for p in file_path.split(",")
        if p.strip() and not p.strip().startswith(_FOLDER_MARKER_PREFIX)
    ]


def _extract_folder_marker(file_path: str) -> Optional[str]:
    """从 file_path 中提取文件夹来源路径；若非文件夹来源则返回 None。"""
    for part in file_path.split(","):
        part = part.strip()
        if part.startswith(_FOLDER_MARKER_PREFIX):
            return part[len(_FOLDER_MARKER_PREFIX):]
    return None


def _record_looks_like_image(record: dict) -> bool:
    """根据 file_type 或路径扩展名判断记录是否为图文任务。"""
    ft = (record.get("file_type") or "").lower()
    if ft == "image":
        return True
    if ft == "video":
        return False
    fp = record.get("file_path") or ""
    paths = [p.strip().lower() for p in _split_comma_paths(fp)]
    return any(
        p.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"))
        for p in paths
    )


class SingleTaskCreationPage(TrackedTaskMixin, BasePage):
    """单视频 / 单个图文发布页面（由 media_mode 区分）"""
    
    # 发布完成信号
    publish_completed = Signal(bool, str)  # (success, message)
    
    _lazy_content = True

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        page_title: str = "单个视频任务",
        media_mode: Literal["video", "image"] = "video",
    ):
        """初始化
        
        Args:
            parent: 父控件
            page_title: 页面标题（导航/BasePage）
            media_mode: video=单视频；image=单个图文（可多图路径，英文逗号拼接存储）
        """
        super().__init__(page_title, parent)
        self._media_mode: Literal["video", "image"] = media_mode
        from src.services.auth import CurrentUserService
        self._current_user_svc = CurrentUserService()
        self.user_id = self._current_user_svc.get_user_id_or_default(1)
        self.account_manager = None
        self.selected_file_path = ""
        self.selected_account = None
        self._file_from_auto_library = False
        self._single_auto_apply_generation = 0
        self._copywriting_auto_apply_generation = 0
        self.editing_record_id = None
        # 从列表/记录进入编辑时记录保存前的 status，用于失败任务保存后改回待发布
        self._editing_record_original_status: Optional[str] = None
        # 编辑时记录原始任务源（group/account），用于判断是否需要保留账号组标记
        self._editing_record_original_task_source: Optional[str] = None
        # 编辑时记录原始素材路径，用于判断用户是否更换了视频/图片
        self._editing_record_original_file_path: Optional[str] = None
        # 从「待发布 / 已发布 / 回收站」哪一页进入编辑；点「返回」时回到该页；「保存修改」成功后一律去待发布
        self._publish_edit_return_route: Optional[str] = None
        self.available_accounts: List[dict] = []
        self._accounts_loading = False
        self._init_task_tracking()
        self._creation_controller = SingleTaskCreationController(self)

        self._init_services()

    @property
    def _is_image_mode(self) -> bool:
        return self._media_mode == "image"

    def _empty_file_hint(self) -> str:
        return "暂未选择图片" if self._is_image_mode else "暂未选择视频"

    def _preview_placeholder_text(self) -> str:
        return "图片预览窗口" if self._is_image_mode else "视频预览窗口"

    def _first_cover_radio_text(self) -> str:
        return "首张封面" if self._is_image_mode else "首帧封面"

    def _cover_section_title(self) -> str:
        return "图文封面" if self._is_image_mode else "视频封面"

    def _cover_type_is_local(self) -> bool:
        combo = getattr(self, "cover_type_combo", None)
        if combo is None:
            return False
        return combo.currentData() == _COVER_TYPE_LOCAL

    def _set_cover_type_combo(self, cover_type: str) -> None:
        combo = getattr(self, "cover_type_combo", None)
        if combo is None:
            return
        for i in range(combo.count()):
            if combo.itemData(i) == cover_type:
                combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(False)
                self._on_cover_type_changed()
                return

    def _set_account_label_placeholder(self) -> None:
        """未选账号/组时的默认提示（非错误态）。"""
        if not hasattr(self, "account_label") or not self.account_label:
            return
        self.account_label.setText(_ACCOUNT_LABEL_PLACEHOLDER)
        self.account_label.setStyleSheet(
            f"color: {_theme_colors()['hint_text']}; margin-left: 10px;"
        )

    @staticmethod
    def _path_looks_like_image(path: str) -> bool:
        return path.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"))

    def _resolve_preview_path(self, file_path: str) -> Optional[str]:
        """从单路径或逗号分隔路径中取第一个存在的文件，用于预览。"""
        for p in _split_comma_paths(file_path):
            if os.path.exists(p):
                return p
        return None

    def _disconnect_preview_first_frame_arm(self, w: Optional[QWidget]) -> None:
        """取消首帧预览用的 mediaStatus 监听，并使进行中的首帧脉冲失效。"""
        self._cancel_base_page_timer("preview_first_frame")
        if w is None:
            return
        h = getattr(self, "_preview_first_frame_handler", None)
        if h is not None:
            try:
                w.player.mediaStatusChanged.disconnect(h)  # type: ignore
            except TypeError:
                pass
            self._preview_first_frame_handler = None
        self._preview_first_frame_generation = getattr(self, "_preview_first_frame_generation", 0) + 1

    def _complete_preview_first_frame(self, gen: int, player) -> None:
        """短暂 play 后暂停在 0ms，让多数后端在 VideoWidget 上画出首帧。"""
        if gen != getattr(self, "_preview_first_frame_generation", 0):
            return
        try:
            player.pause()
            player.setPosition(0)
            player.setMuted(False)
        except Exception:
            pass

    def _arm_preview_video_first_frame(self, w: QWidget) -> None:
        """媒体就绪后触发一次静音短播，用于首帧预览（避免仅 setSource 时画面全黑）。"""
        from PySide6.QtMultimedia import QMediaPlayer

        player = w.player  # type: ignore
        self._disconnect_preview_first_frame_arm(w)
        self._preview_first_frame_generation = getattr(self, "_preview_first_frame_generation", 0) + 1
        gen = self._preview_first_frame_generation

        def on_status(status: QMediaPlayer.MediaStatus) -> None:
            if status not in (
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.BufferedMedia,
            ):
                return
            try:
                player.mediaStatusChanged.disconnect(on_status)
            except TypeError:
                return
            self._preview_first_frame_handler = None
            try:
                player.setMuted(True)
                player.setPosition(0)
                player.play()
                self._schedule_base_page_timer(
                    "preview_first_frame",
                    120,
                    lambda gen=gen, player=player: self._complete_preview_first_frame(gen, player),
                )
            except Exception as e:
                logger.debug("首帧预览触发失败: %s", e)

        self._preview_first_frame_handler = on_status
        player.mediaStatusChanged.connect(on_status)

    def _update_preview_video_source(self, file_path: str) -> None:
        """将下方 Fluent VideoWidget 绑定到本地视频文件；无有效视频路径时停止并清空。"""
        if self._is_image_mode:
            return
        if getattr(self, "preview_video_widget", None) is None and not (file_path or "").strip():
            return
        w = self._ensure_preview_video_widget()
        if w is None:
            return
        resolved: Optional[str] = None
        if file_path and file_path.strip():
            resolved = self._resolve_preview_path(file_path.strip())
        if resolved and os.path.isfile(resolved) and not self._path_looks_like_image(resolved):
            try:
                self._disconnect_preview_first_frame_arm(w)
                w.stop()  # type: ignore
                w.setVideo(QUrl.fromLocalFile(os.path.normpath(os.path.abspath(resolved))))  # type: ignore
                self._arm_preview_video_first_frame(w)
            except Exception as e:
                logger.warning("设置预览视频源失败: %s", e)
        else:
            try:
                self._disconnect_preview_first_frame_arm(w)
                w.pause()  # type: ignore
                w.player.setSource(QUrl())  # type: ignore
            except Exception as e:
                logger.debug("清空预览视频源: %s", e)

    def _set_file_info_label_for_paths(self, paths: List[str]) -> None:
        """根据已选路径列表更新文件信息标签（图文支持多图）。"""
        if not paths or not hasattr(self, "file_info_label") or not self.file_info_label:
            return
        existing = [p for p in paths if os.path.exists(p)]
        if not existing:
            self.file_info_label.setText(self._empty_file_hint())
            return
        total = sum(os.path.getsize(p) for p in existing)
        size_mb = total / (1024 * 1024)
        n = len(existing)
        base = os.path.basename(existing[0])
        if n == 1:
            self.file_info_label.setText(f"{base} | 大小: {size_mb:.2f} MB")
        else:
            self.file_info_label.setText(f"{base} 等共 {n} 张 | 合计: {size_mb:.2f} MB")
        
    def showEvent(self, event):
        """页面显示时触发账号加载（此时 qasync 事件循环已就绪）"""
        super().showEvent(event)
        if self.available_accounts or self._accounts_loading:
            self._schedule_preview_video_idle_init(delay_ms=1200)
            return
        if self._try_apply_cached_accounts():
            self._schedule_accounts_refresh(delay_ms=800)
            self._schedule_preview_video_idle_init(delay_ms=1200)
            return
        mode_zh = "图文" if self._is_image_mode else "视频"
        logger.info("showEvent: %s任务页首次显示，加载账号列表…", mode_zh)
        self._accounts_loading = True
        self._create_tracked_task(
            self._load_accounts(),
            name="ui.single_publish.load_accounts",
        )
        self._schedule_preview_video_idle_init(delay_ms=1200)

    def _try_apply_cached_accounts(self) -> bool:
        try:
            from src.services.account.account_list_cache import get_cached_accounts

            cached = get_cached_accounts()
            if cached is None:
                return False
            self.available_accounts = cached
            self._apply_accounts_to_ui()
            logging.getLogger("ui.perf").debug(
                "[页面耗时] account load cache single_task_creation_page: %d accounts",
                len(cached),
            )
            return True
        except Exception as e:
            logger.debug("读取账号列表缓存失败: %s", e)
            return False

    def _schedule_accounts_refresh(self, *, delay_ms: int = 1000) -> None:
        if self._accounts_loading:
            return

        def _refresh() -> None:
            if self._accounts_loading:
                return
            self._accounts_loading = True
            self._create_tracked_task(
                self._load_accounts(),
                name="ui.single_publish.refresh_accounts",
            )

        self._schedule_base_page_timer("single_accounts_refresh", delay_ms, _refresh)

    def _apply_accounts_to_ui(self) -> None:
        if not hasattr(self, "btn_select_account") or not hasattr(self, "account_label"):
            return
        if self.selected_account:
            self.btn_select_account.setEnabled(bool(self.available_accounts))
            self._update_publish_button_state()
            return
        if self.available_accounts:
            self.btn_select_account.setEnabled(True)
            self._set_account_label_placeholder()
        elif getattr(self, "_accounts_loading", False):
            self.btn_select_account.setEnabled(True)
            self._set_account_label_placeholder()
        else:
            self.account_label.setText("无可用发布账号 (请先添加并登录)")
            self.account_label.setStyleSheet(
                "color: red; font-weight: bold; margin-left: 10px;"
            )
            self.btn_select_account.setEnabled(False)
        self._update_publish_button_state()

    def _track_task(self, task: asyncio.Task) -> asyncio.Task:
        """跟踪异步任务，自动清理已完成任务并记录异常"""
        return super()._track_task(task)

    def _on_task_done(self, task: asyncio.Task):
        """任务完成回调：移除引用并记录未捕获异常"""
        super()._on_task_done(task)

    def closeEvent(self, event):
        """页面关闭时取消所有未完成的异步任务"""
        self._release_preview_video_player()
        self._cancel_tracked_tasks()
        super().closeEvent(event)

    def _release_preview_video_player(self) -> None:
        """离开页面/退出前停止 Qt Multimedia，减轻退出时 QThreadStorage 告警。"""
        w = getattr(self, "preview_video_widget", None)
        if w is None or self._is_image_mode:
            return
        try:
            self._disconnect_preview_first_frame_arm(w)
            w.stop()
            w.player.stop()
            w.player.setSource(QUrl())
        except Exception as e:
            logger.debug("释放预览播放器: %s", e)

    def prewarm_for_fast_show(self, *, preview_delay_ms: int = 2500) -> bool:
        """Build hidden content during startup idle so first navigation only switches pages."""
        try:
            if self.isVisible() or getattr(self, "_content_initialized", False):
                return False
            import time
            from src.utils.startup_profiler import is_page_load_profiler_enabled

            t0 = time.perf_counter() if is_page_load_profiler_enabled() else 0.0
            self._ensure_content()
            self._try_apply_cached_accounts()
            self._schedule_accounts_refresh(delay_ms=1200)
            self._schedule_preview_video_idle_init(delay_ms=preview_delay_ms)
            if is_page_load_profiler_enabled():
                logging.getLogger("ui.perf").info(
                    "[页面耗时] single page prewarm content: %.0f ms",
                    (time.perf_counter() - t0) * 1000,
                )
            return True
        except Exception as e:
            logger.debug("单视频任务页预热失败: %s", e, exc_info=True)
            return False

    def _schedule_preview_video_idle_init(self, *, delay_ms: int) -> None:
        if self._is_image_mode or getattr(self, "preview_video_widget", None) is not None:
            return
        if getattr(self, "_preview_video_card", None) is None:
            return
        self._schedule_base_page_timer(
            "preview_video_widget_idle_init",
            max(0, delay_ms),
            lambda: self._ensure_preview_video_widget(),  # type: ignore
        )
    
    def _apply_preview_placeholder_style(self):
        """为预览区 label 应用空状态样式（主题感知）"""
        if getattr(self, "preview_label", None) is None:
            return
        tc = _theme_colors()
        self.preview_label.setStyleSheet(  # type: ignore
            f"background-color: {tc['preview_bg']}; border: 2px dashed {tc['preview_border']}; "
            f"border-radius: 12px; color: {tc['preview_text']}; font-weight: bold;"
        )

    def _init_services(self):
        """初始化服务"""
        try:
            from src.infrastructure.common.di.service_locator import ServiceLocator
            from src.services.account.account_manager_async import AccountManagerAsync
            from src.infrastructure.common.event.event_bus import EventBus
            from src.services.account.account_group_service import AccountGroupService
            
            service_locator = ServiceLocator()
            event_bus = service_locator.get(EventBus)
            
            # 创建账号管理器（已迁移为 Repository 模式）
            self.account_manager = AccountManagerAsync(
                user_id=self.user_id,
                event_bus=event_bus
            )
            # 创建账号组服务（待迁移为 AccountGroupRepositoryAsync）
            self.group_service = AccountGroupService()
        except Exception as e:
            logger.error(f"初始化单发布页面服务失败: {e}", exc_info=True)
    
    def _setup_content(self):
        """设置内容"""
        import time
        from src.utils.startup_profiler import is_page_load_profiler_enabled

        _fallback_visible = self.isVisible()
        _setup_t0 = time.perf_counter() if is_page_load_profiler_enabled() else 0.0
        # 创建滚动区域
        self.scroll_area = SmoothScrollArea(self)  # type: ignore
        self.scroll_area.setScrollAnimation(Qt.Vertical, 400, QEasingCurve.OutQuint)  # type: ignore
        self.scroll_area.setScrollAnimation(Qt.Horizontal, 400, QEasingCurve.OutQuint)  # type: ignore
            
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)  # type: ignore
        # 防止宽度抖动：强制启用垂直滚动条，禁用水平滚动条
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # type: ignore
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)  # type: ignore
        self.scroll_area.setStyleSheet("background: transparent;")
        self.scroll_area.viewport().setStyleSheet("background: transparent;")
        
        # 创建内容容器
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(16, 0, 16, 24)
        layout.setSpacing(16)
        
        # --- 上区双栏：左（账号/视频/作品描述）| 右（预览）；下区全宽与底部操作栏对齐 ---
        main_hbox = QHBoxLayout()
        main_hbox.setSpacing(16)
        main_hbox.setContentsMargins(0, 0, 0, 0)

        left_vbox = QVBoxLayout()
        left_vbox.setSpacing(16)

        core_config_card = self._create_core_config_card()
        description_card = self._create_description_card()
        left_vbox.addWidget(core_config_card)
        left_vbox.addWidget(description_card)

        preview_card = self._create_preview_card()

        main_hbox.addLayout(left_vbox, 1)
        main_hbox.addWidget(
            preview_card, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight
        )

        layout.addLayout(main_hbox)

        self._more_publish_settings_card = MorePublishSettingsCard(
            self, is_image_mode=self._is_image_mode
        )
        schedule_card = self._create_schedule_card()
        layout.addWidget(self._more_publish_settings_card)
        layout.addWidget(schedule_card)
        
        # 发布按钮卡片
        action_card = self._create_action_card()
        layout.addWidget(action_card)

        # 添加弹性空间
        layout.addStretch()

        # 设置滚动区域的内容
        self.scroll_area.setWidget(self.content_widget)
        
        # 将滚动区域添加到BasePage的内容布局中
        self.content_layout.addWidget(self.scroll_area)
        self._set_account_label_placeholder()
        self._refresh_account_dependent_settings_ui()
        if _fallback_visible:
            self._schedule_preview_video_idle_init(delay_ms=1200)
            if is_page_load_profiler_enabled():
                logging.getLogger("ui.perf").info(
                    "[页面耗时] single page first show fallback content: %.0f ms",
                    (time.perf_counter() - _setup_t0) * 1000,
                )

    # ---------- UI 搭建：卡片与区块 (_create_*_card) ----------
    def _create_preview_card(self) -> QWidget:
        """创建独立的预览卡片（图文：280 预览图；视频：仅 Fluent VideoWidget，不再 FFmpeg 抽帧 QLabel）"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0) # 彻底移除内边距，让画面铺满
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter) # type: ignore

        self.preview_label = None
        self.preview_video_widget = None
        self._preview_video_card = card
        self._preview_video_layout = layout

        if self._is_image_mode:
            self.preview_label = QLabel(card)
            self.preview_label.setAlignment(Qt.AlignCenter)  # type: ignore
            self.preview_label.setFixedSize(280, 280)
            self.preview_label.setText(self._preview_placeholder_text())
            self._apply_preview_placeholder_style()
            layout.addWidget(self.preview_label)
        else:
            self.preview_label = QLabel(card)
            self.preview_label.setAlignment(Qt.AlignCenter)  # type: ignore
            self.preview_label.setFixedSize(280, 384)
            self.preview_label.setText(self._preview_placeholder_text())
            self._apply_preview_placeholder_style()
            layout.addWidget(self.preview_label)

        return card

    def _ensure_preview_video_widget(self) -> Optional[QWidget]:
        """Create the Qt Multimedia preview lazily to keep first navigation light."""
        if self._is_image_mode:
            return None
        existing = getattr(self, "preview_video_widget", None)
        if existing is not None:
            return existing
        card = getattr(self, "_preview_video_card", None)
        layout = getattr(self, "_preview_video_layout", None)
        if card is None or layout is None:
            return None
        import time
        from src.utils.startup_profiler import is_page_load_profiler_enabled

        t0 = time.perf_counter() if is_page_load_profiler_enabled() else 0.0
        try:
            from src.ui.components.preview_video_widget import PreviewVideoWidget

            placeholder = getattr(self, "preview_label", None)
            if placeholder is not None:
                layout.removeWidget(placeholder)
                placeholder.deleteLater()
                self.preview_label = None
            self.preview_video_widget = PreviewVideoWidget(card)
            self.preview_video_widget.setMinimumSize(280, 384)
            self.preview_video_widget.setMaximumWidth(280)
            layout.addWidget(self.preview_video_widget)
            return self.preview_video_widget
        except Exception as e:
            logger.warning("内置视频预览播放器不可用: %s", e)
            self.preview_video_widget = None
            return None
        finally:
            if is_page_load_profiler_enabled():
                logging.getLogger("ui.perf").info(
                    "[页面耗时] single page preview idle init: %.0f ms",
                    (time.perf_counter() - t0) * 1000,
                )
    
    def _create_core_config_card(self) -> QWidget:
        """核心配置卡片：发布对象、发布内容（素材）、封面设置。"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        account_row = QHBoxLayout()
        self.btn_select_account = PrimaryPushButton(FluentIcon.PEOPLE, "选择发布对象", card)
        self.account_label = BodyLabel(_ACCOUNT_LABEL_PLACEHOLDER, card)
        self.account_label.setStyleSheet(
            f"color: {_theme_colors()['hint_text']}; margin-left: 10px;"
        )
        self.btn_select_account.clicked.connect(self._on_select_account)
        self.btn_select_account.setFixedWidth(BUTTON_FIXED_WIDTH)

        account_row.addWidget(self.btn_select_account)
        account_row.addWidget(self.account_label, 1)
        layout.addLayout(account_row)

        video_row = QHBoxLayout()
        add_icon = FluentIcon.PHOTO if self._is_image_mode else FluentIcon.VIDEO
        add_label = "添加图片" if self._is_image_mode else "添加视频"
        self.btn_add_video = PrimaryPushButton(add_icon, add_label, card)
        self.file_info_label = BodyLabel(self._empty_file_hint(), card)
        
        self.file_info_label.setWordWrap(True)
        self.btn_add_video.clicked.connect(self._on_browse_file)
        self.btn_add_video.setFixedWidth(BUTTON_FIXED_WIDTH)
        self.file_info_label.setStyleSheet(f"color: {_theme_colors()['hint_text']}; margin-left: 10px;")
        
        video_row.addWidget(self.btn_add_video)
        # 图文模式：在「添加图片」右侧加「添加图片文件夹」按钮
        self.btn_add_image_folder = None
        if self._is_image_mode:
            self.btn_add_image_folder = PushButton(FluentIcon.FOLDER, "添加图片文件夹", card)
            self.btn_add_image_folder.setFixedWidth(BUTTON_FIXED_WIDTH + 20)
            self.btn_add_image_folder.clicked.connect(self._on_browse_image_folder)
            video_row.addWidget(self.btn_add_image_folder)
        # 单视频页：QFluentWidgets SwitchButton，开启后从媒体库自动取一条，与「添加视频」互斥
        self._auto_match_video_switch = None
        if not self._is_image_mode:
            auto_wrap = QWidget(card)
            auto_l = QHBoxLayout(auto_wrap)
            auto_l.setContentsMargins(0, 0, 0, 0)
            auto_l.setSpacing(6)
            lbl_auto = BodyLabel("视频库自动匹配", card)
            lbl_auto.setStyleSheet(f"color: {_theme_colors()['hint_text']};")
            self._auto_match_video_switch = SwitchButton(card)
            self._auto_match_video_switch.setOnText("开")
            self._auto_match_video_switch.setOffText("关")
            _tip_am = (
                "开启后从所选账号或账号组在媒体库中的「视频 → 未发布」目录按文件名顺序取一条视频；"
                "与批量发布自动匹配规则一致，不含公共视频库根目录未分配文件。"
            )
            apply_instructional_tooltip(
                _tip_am,
                lbl_auto,
                self._auto_match_video_switch,
                position=ToolTipPosition.BOTTOM,
            )
            auto_l.addWidget(lbl_auto)
            auto_l.addWidget(self._auto_match_video_switch, 0, Qt.AlignmentFlag.AlignVCenter)
            video_row.addWidget(auto_wrap, 0, Qt.AlignmentFlag.AlignVCenter)
            self._auto_match_video_switch.blockSignals(True)
            self._auto_match_video_switch.setChecked(load_persisted_single_auto_match_video_library())
            self._auto_match_video_switch.blockSignals(False)
            self._auto_match_video_switch.checkedChanged.connect(self._on_auto_match_video_switch_changed)
            if self._auto_match_video_switch.isChecked():
                self.btn_add_video.setEnabled(False)
        video_row.addWidget(self.file_info_label, 1)
        layout.addLayout(video_row)

        cover_row = QHBoxLayout()
        cover_title = BodyLabel("封面类型", card)

        self.cover_type_combo = ComboBox(card)
        self.cover_type_combo.addItem(
            self._first_cover_radio_text(), userData=_COVER_TYPE_FIRST_FRAME
        )
        self.cover_type_combo.addItem("本地封面", userData=_COVER_TYPE_LOCAL)
        self.cover_type_combo.setFixedWidth(COVER_TYPE_COMBO_WIDTH)
        self.cover_type_combo.setCurrentIndex(0)

        self.cover_path_label = BodyLabel("未选择本地封面", card)
        self.cover_path_label.setStyleSheet(f"color: {_theme_colors()['hint_text']}; margin-left: 10px;")
        self.cover_path_label.setWordWrap(True)
        self.selected_cover_path = ""

        self.btn_browse_cover = PushButton(FluentIcon.PHOTO, "选择", card)

        cover_title.setFixedWidth(_SETTINGS_LABEL_WIDTH)

        self.btn_browse_cover.setEnabled(False)

        self.cover_type_combo.currentIndexChanged.connect(self._on_cover_type_changed)
        self.btn_browse_cover.clicked.connect(self._on_browse_cover)

        cover_row.setSpacing(12)
        cover_row.addWidget(cover_title)
        cover_row.addWidget(self.cover_type_combo)
        cover_row.addWidget(self.btn_browse_cover)
        cover_row.addWidget(self.cover_path_label, 1)
        layout.addLayout(cover_row)
        
        return card
    
    def _create_description_card(self) -> QWidget:
        """创建作品描述独立卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        
        # 标题 (作品描述)
        title = SubtitleLabel("作品描述", card)
        layout.addWidget(title)

        # 单视频：文案库自动匹配（开关与模式在描述卡片内，与标题/简介输入区相邻）
        self._copywriting_auto_switch = None
        if not self._is_image_mode:
            cw_wrap = QWidget(card)
            cw_l = QHBoxLayout(cw_wrap)
            cw_l.setContentsMargins(0, 0, 0, 0)
            cw_l.setSpacing(8)
            lbl_cw = BodyLabel("文案匹配", card)
            lbl_cw.setStyleSheet(f"color: {_theme_colors()['hint_text']};")
            self._copywriting_auto_switch = SwitchButton(card)
            self._copywriting_auto_switch.setOnText("开")
            self._copywriting_auto_switch.setOffText("关")

            self._copywriting_mode_combo = ComboBox(card)
            self._copywriting_mode_combo.addItem("标准库", userData=CopywritingMatchMode.STANDARD)
            self._copywriting_mode_combo.addItem("随机(全库)", userData=CopywritingMatchMode.RANDOM_ALL)
            self._copywriting_mode_combo.addItem("随机(分类)", userData=CopywritingMatchMode.RANDOM_CATEGORY)
            # Fluent ComboBox 为按钮绘制文案，固定过窄会截断「随机(全库)」等选项
            _cw_fm = QFontMetrics(card.font())
            _mode_text_w = max(
                _cw_fm.horizontalAdvance(t)
                for t in ("标准库", "随机(全库)", "随机(分类)")
            )
            self._copywriting_mode_combo.setMinimumWidth(_mode_text_w + 44)

            self._copywriting_category_combo = ComboBox(card)
            self._copywriting_category_combo.hide()
            self._copywriting_category_combo.setMinimumWidth(
                max(160, _cw_fm.horizontalAdvance("选择分类...") + 44)
            )

            _tip_cw = (
                "开启后，自动填充作品标题与描述。\n"
                "标准库：按文件名前5位作品编号（如 A0001）匹配；\n"
                "随机库：从随机文案库中抽取。"
            )
            apply_instructional_tooltip(
                _tip_cw,
                lbl_cw,
                self._copywriting_auto_switch,
                position=ToolTipPosition.BOTTOM,
            )
            cw_l.addWidget(lbl_cw)
            cw_l.addWidget(self._copywriting_auto_switch, 0, Qt.AlignmentFlag.AlignVCenter)
            cw_l.addWidget(self._copywriting_mode_combo, 0, Qt.AlignmentFlag.AlignVCenter)
            cw_l.addWidget(self._copywriting_category_combo, 0, Qt.AlignmentFlag.AlignVCenter)
            cw_l.addStretch(1)
            layout.addWidget(cw_wrap)

            self._copywriting_auto_switch.blockSignals(True)
            self._copywriting_auto_switch.setChecked(load_persisted_single_auto_match_copywriting())
            self._copywriting_auto_switch.blockSignals(False)

            mode = load_persisted_single_copywriting_match_mode()
            idx = self._copywriting_mode_combo.findData(mode)
            if idx >= 0:
                self._copywriting_mode_combo.setCurrentIndex(idx)

            self._copywriting_auto_switch.checkedChanged.connect(self._on_copywriting_auto_switch_changed)
            self._copywriting_mode_combo.currentIndexChanged.connect(self._on_copywriting_mode_changed)
            self._copywriting_category_combo.currentIndexChanged.connect(self._on_copywriting_category_changed)

            self._schedule_base_page_timer(
                "copywriting_categories_refresh",
                0,
                self._refresh_copywriting_categories_async,
            )
            self._update_copywriting_ui_visibility()

        # 一体化容器
        entry_container = QFrame(card)
        entry_container.setObjectName("EntryContainer")
        tc = _theme_colors()
        entry_container.setStyleSheet(f"""
            #EntryContainer {{
                border: 1px solid {tc['entry_border']};
                border-radius: 8px;
                background-color: {tc['entry_bg']};
            }}
            #EntryContainer:hover {{
                border-color: {tc['entry_hover_border']};
            }}
        """)
        container_layout = QVBoxLayout(entry_container)
        container_layout.setContentsMargins(10, 4, 10, 4)
        container_layout.setSpacing(0)
        
        # (1) 标题行: 输入框 + 字数
        title_hbox = QHBoxLayout()
        self.title_edit = LineEdit(entry_container)
            
        self.title_edit.setPlaceholderText("填写作品标题，为作品获得更多流量")
        self.title_edit.setStyleSheet("border: none; background: transparent; font-size: 14px; padding: 2px 0;")
        
        title_count_label = QLabel(f"0/{TITLE_MAX_LENGTH}", entry_container)
        title_count_label.setStyleSheet(f"color: {tc['count_text']}; font-size: 12px;")
        
        title_hbox.addWidget(self.title_edit)
        title_hbox.addWidget(title_count_label)
        container_layout.addLayout(title_hbox)
        
        # (2) 分割线
        line = QFrame(entry_container)
        line.setFrameShape(QFrame.HLine)  # type: ignore
        line.setFrameShadow(QFrame.Plain)  # type: ignore
        line.setStyleSheet(f"background-color: {tc['separator']}; max-height: 1px; margin: 1px 0;")
        container_layout.addWidget(line)
        
        # (3) 描述文本区（QTextEdit 支持富文本，用于 #关键词+空格 话题高亮）
        self.desc_edit = QTextEdit(entry_container)
        self.desc_edit.setPlaceholderText("添加作品描述")
        self.desc_edit.setAcceptRichText(True)
        self.desc_edit.setStyleSheet("border: none; background: transparent; font-size: 14px; padding: 2px 0;")
        # 更矮的编辑区：长文在框内滚动
        self.desc_edit.setMinimumHeight(36)
        self.desc_edit.setMaximumHeight(72)
        self.desc_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        container_layout.addWidget(self.desc_edit)
        
        # (4) 底部工具栏: 话题、@常用词 + 话题数 + 字数统计
        toolbar_hbox = QHBoxLayout()
        toolbar_hbox.setContentsMargins(0, 0, 0, 0)
        
        self.btn_topic = PushButton("#添加话题", entry_container)
        self.btn_mention = PushButton("@好友", entry_container)
            
        btn_style = f"border: none; background: transparent; color: {tc['hint_text']}; font-size: 13px; font-weight: 500; padding: 4px 8px;"
        self.btn_topic.setStyleSheet(btn_style)
        self.btn_mention.setStyleSheet(btn_style + "margin-left: 4px;")
        self.btn_topic.setCursor(Qt.PointingHandCursor)  # type: ignore
        self.btn_mention.setCursor(Qt.PointingHandCursor)  # type: ignore
        
        self.btn_topic.clicked.connect(self._on_add_topic_clicked)
        self.btn_mention.clicked.connect(self._on_add_mention_clicked)
        
        self.topic_count_label = QLabel("已设置 0 个话题", entry_container)
        self.topic_count_label.setStyleSheet(f"color: {tc['hint_text']}; font-size: 12px; margin-left: 8px;")
        
        total_count_label = QLabel("0 / 1000", entry_container)
        total_count_label.setStyleSheet(f"color: {tc['count_text']}; font-size: 12px;")
        
        # 实时统计字数 + 话题识别与高亮
        self.title_edit.textChanged.connect(lambda text: title_count_label.setText(f"{len(text)}/{TITLE_MAX_LENGTH}"))
        self._desc_total_count_label = total_count_label
        self._work_desc_controller = WorkDescriptionEditController(
            self,
            self.desc_edit,
            char_limit=1000,
            char_count_label=total_count_label,
            topic_count_label=self.topic_count_label,
            topic_count_format="已设置 {} 个话题",
        )

        toolbar_hbox.addWidget(self.btn_topic)
        toolbar_hbox.addWidget(self.btn_mention)
        toolbar_hbox.addWidget(self.topic_count_label)
        toolbar_hbox.addStretch()
        toolbar_hbox.addWidget(total_count_label)
        container_layout.addLayout(toolbar_hbox)
        
        layout.addWidget(entry_container)
        return card

    def _on_add_topic_clicked(self) -> None:
        """在作品描述中插入话题符号。"""
        self.desc_edit.insertPlainText("#")
        self.desc_edit.setFocus()

    def _on_add_mention_clicked(self) -> None:
        """在作品描述中插入 @ 符号。"""
        self.desc_edit.insertPlainText("@")
        self.desc_edit.setFocus()

    def _selected_account_platform_for_widgets(self) -> str:
        """当前选中账号/组用于位置库、购物车等控件的平台 id。"""
        sel = getattr(self, "selected_account", None)
        if not sel or not isinstance(sel, dict):
            return ""
        if sel.get("type") == "account":
            return (sel.get("data") or {}).get("platform") or ""
        if sel.get("type") == "group":
            platforms = (sel.get("data") or {}).get("platforms") or []
            if not platforms:
                return ""
            first = platforms[0]
            if isinstance(first, dict):
                return (first.get("platform") or "").strip()
            return (str(first) if first is not None else "").strip()
        return ""

    def _platforms_in_selected_publish_target(self) -> Set[str]:
        """当前选中的发布对象涉及的平台 id 集合（小写，用于右栏按平台显隐）。"""
        sel = getattr(self, "selected_account", None)
        if not sel or not isinstance(sel, dict):
            return set()
        plats: List[str] = []
        if sel.get("type") == "account":
            p = ((sel.get("data") or {}).get("platform") or "").strip().lower()
            return {p} if p else set()
        if sel.get("type") == "group":
            grp = sel.get("data") or {}
            for a in grp.get("accounts") or []:
                if not isinstance(a, dict):
                    continue
                x = (a.get("platform") or "").strip().lower()
                if x:
                    plats.append(x)
            for x in grp.get("platforms") or []:
                if isinstance(x, dict):
                    px = (x.get("platform") or "").strip().lower()
                    if px:
                        plats.append(px)
                elif isinstance(x, str) and x.strip():
                    plats.append(x.strip().lower())
            return set(plats)
        return set()

    def _refresh_more_publish_settings_ui(self) -> None:
        """刷新「更多发布设置」卡片。"""
        card = getattr(self, "_more_publish_settings_card", None)
        if card is None:
            return
        card.refresh(
            self._work_declaration_effective_context(),
            location_platform=self._selected_account_platform_for_widgets(),
            platforms_in_selection=self._platforms_in_selected_publish_target(),
        )
        platform = self._selected_account_platform_for_widgets()
        if platform:
            card.refresh_yellow_cart_platform(platform)

    def _work_declaration_effective_context(self) -> str:
        """返回当前应展示的作品申明上下文：平台 id、mixed、none。"""
        sel = getattr(self, "selected_account", None)
        if not sel or not isinstance(sel, dict):
            return "none"
        if sel.get("type") == "account":
            acc = sel.get("data") or {}
            p = (acc.get("platform") or "").strip()
            return p if p else "none"
        if sel.get("type") == "group":
            grp = sel.get("data") or {}
            plats: List[str] = []
            for a in grp.get("accounts") or []:
                if not isinstance(a, dict):
                    continue
                x = (a.get("platform") or "").strip()
                if x:
                    plats.append(x)
            if not plats:
                for x in grp.get("platforms") or []:
                    if isinstance(x, str) and x.strip():
                        plats.append(x.strip())
            uniq = list(dict.fromkeys(plats))
            if len(uniq) == 1:
                return uniq[0]
            if len(uniq) > 1:
                return "mixed"
            return "none"
        return "none"

    def _refresh_account_dependent_settings_ui(
        self, *, sync_work_declaration_from_storage: bool = True
    ) -> None:
        """账号变化时刷新更多发布设置（sync 参数保留兼容，申明由新卡自行处理）。"""
        del sync_work_declaration_from_storage
        self._refresh_more_publish_settings_ui()

    def _create_schedule_card(self) -> QWidget:
        """创建「发布时间」独立卡片。"""
        card = CardWidget(self)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(_SETTINGS_ROW_GAP)

        layout.addWidget(SubtitleLabel("发布时间", card))

        schedule_row = QHBoxLayout()
        schedule_row.setContentsMargins(0, 0, 0, 0)
        schedule_row.setSpacing(_SETTINGS_H_GAP)
        schedule_label = BodyLabel("发布时间", card)
        schedule_label.setFixedWidth(_SETTINGS_LABEL_WIDTH)
        schedule_content = QVBoxLayout()
        schedule_content.setContentsMargins(0, 0, 0, 0)
        schedule_content.setSpacing(0)
        self._init_schedule_ui(schedule_content, card)
        schedule_row.addWidget(schedule_label)
        schedule_row.addLayout(schedule_content, 1)
        layout.addLayout(schedule_row)

        return card

    def _init_schedule_ui(self, layout, parent):
        """初始化定时发布UI (立即/定时)"""
        option_row = QHBoxLayout()
        option_row.setContentsMargins(0, 0, 0, 0)
        option_row.setSpacing(_SETTINGS_H_GAP)

        self.radio_now = RadioButton("立即发布")
        self.radio_schedule = RadioButton("定时发布")
        self.radio_now.setChecked(True)
        self.radio_now.setFocusPolicy(Qt.NoFocus)  # type: ignore
        self.radio_schedule.setFocusPolicy(Qt.NoFocus)  # type: ignore

        self.publish_time_group = QButtonGroup(parent)
        self.publish_time_group.addButton(self.radio_now)
        self.publish_time_group.addButton(self.radio_schedule)

        self.date_picker = create_fast_calendar_picker(parent)
        self.time_picker = TimePicker(parent)
        for col in (0, 1):
            self.time_picker.setColumnWidth(col, SCHEDULE_TIME_PICKER_COL_WIDTH)
        self._apply_default_schedule_datetime()

        option_row.addWidget(self.radio_now)
        option_row.addWidget(self.radio_schedule)
        option_row.addWidget(self.date_picker)
        option_row.addWidget(self.time_picker)
        option_row.addStretch()

        layout.addLayout(option_row)
        
        # 连接信号进行校验
        self.date_picker.dateChanged.connect(self._validate_schedule_time)
        self.time_picker.timeChanged.connect(self._validate_schedule_time)
        
        # 立即发布时隐藏；切换到定时发布时显示并刷新默认时间为「当前 + 2.5 小时」
        self.date_picker.setVisible(False)
        self.time_picker.setVisible(False)
        self.radio_schedule.toggled.connect(self._on_schedule_mode_toggled)

    def _default_scheduled_datetime(self) -> QDateTime:
        return QDateTime.currentDateTime().addSecs(SCHEDULE_MIN_LEAD_SECS)

    def _apply_default_schedule_datetime(self) -> None:
        """将日期时间设为「当前时刻 + 2.5 小时」，程序化更新时不触发校验。"""
        target = self._default_scheduled_datetime()
        self.date_picker.blockSignals(True)
        self.time_picker.blockSignals(True)
        try:
            self.date_picker.setDate(target.date())
            self.time_picker.setTime(target.time())
        finally:
            self.date_picker.blockSignals(False)
            self.time_picker.blockSignals(False)

    def _on_schedule_mode_toggled(self, checked: bool) -> None:
        self.date_picker.setVisible(checked)
        self.time_picker.setVisible(checked)
        if checked:
            self._apply_default_schedule_datetime()

    def _validate_schedule_time(self):
        """校验定时时间：必须至少在当前时间 2.5 小时后，最多 15 天内"""
        # 防止递归调用
        if getattr(self, '_is_validating_time', False):
            return
            
        if not self.date_picker.date.isValid() or not self.time_picker.time.isValid():  # type: ignore
            return
            
        selected_dt = QDateTime(self.date_picker.date, self.time_picker.time)  # type: ignore
        now = QDateTime.currentDateTime()
        min_dt = now.addSecs(SCHEDULE_MIN_LEAD_SECS)
        max_dt = now.addDays(15)        # +15 days
        
        if selected_dt < min_dt:
            self._is_validating_time = True
            
            # 重置为最小合法时间
            target_dt = min_dt.addSecs(300)  # 加 5 分钟缓冲
            self.date_picker.setDate(target_dt.date())
            self.time_picker.setTime(target_dt.time())
            
            InfoBar.warning(
                "时间已修正",
                "定时发布必须至少设置在 2.5 小时以后",
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self.window()
            )
            
            self._is_validating_time = False
        elif selected_dt > max_dt:
            self._is_validating_time = True
            
            # 重置为最大合法时间（向前回调到 15 天边界，时间保持不变）
            self.date_picker.setDate(max_dt.date())
            
            InfoBar.warning(
                "时间已修正",
                "定时发布最多只能设置在 15 天以内",
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self.window()
            )
            
            self._is_validating_time = False


    

    def _create_action_card(self) -> QWidget:
        """创建操作按钮卡片"""
        card = CardWidget(self)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        
        # 状态标签
        self.status_label = BodyLabel("准备就绪", card)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # 清空设置按钮（在发布按钮左侧）
        self.btn_clear_settings = PushButton(FluentIcon.DELETE, "清空设置", card)
        self.btn_clear_settings.clicked.connect(self._reset_form_to_new_page)
        layout.addWidget(self.btn_clear_settings)

        # 从发布列表「编辑」进入编辑时显示：在「保存修改」左侧，放弃修改并回到待发布列表
        self.btn_return_to_publish = PushButton(FluentIcon.RETURN, "返回", card)
        self.btn_return_to_publish.clicked.connect(self._on_return_without_save)
        self.btn_return_to_publish.setVisible(False)
        layout.addWidget(self.btn_return_to_publish)
        
        # 发布按钮 (改为添加到发布列表)
        self.btn_publish = PrimaryPushButton(FluentIcon.ADD, "添加到发布列表", card)
        self.btn_publish.clicked.connect(self._on_publish)
        self.btn_publish.setEnabled(False)
        layout.addWidget(self.btn_publish)
        layout.addSpacing(32) # 右侧留白，使按钮左移
        
        return card

    def _on_return_without_save(self):
        """从发布管理子页「编辑」进入后放弃修改，不写库，回到进入前的子页（待发布/已发布/回收站）。"""
        try:
            route = (getattr(self, "_publish_edit_return_route", None) or "").strip() or "publish_list_page"
            self._publish_edit_return_route = None
            self._reset_form_to_new_page()
            main_window = self.window()
            if hasattr(main_window, "navigate_to"):
                main_window.navigate_to(route)
            else:
                if hasattr(main_window, "_get_or_create_page"):
                    back_page = main_window._get_or_create_page(route)
                    if back_page and hasattr(main_window, "switchTo"):
                        main_window.switchTo(back_page)
                if hasattr(main_window, "navigationInterface"):
                    main_window.navigationInterface.setCurrentItem(route)
        except Exception as e:
            logger.error("返回发布列表失败: %s", e, exc_info=True)
    
    async def _load_accounts(self):
        """异步加载全部平台账号列表"""
        logger.info("SingleTaskCreationPage 准备加载可用账号列表...")
        if not hasattr(self, 'account_manager') or not self.account_manager:
            logger.warning("account_manager 未初始化，放弃加载账号。")
            self._accounts_loading = False
            return
        
        # 直接从数据库获取全部账号，跳过 PlatformRegistry（发布页未注册适配器）
        try:
            import time
            from src.services.account.account_list_cache import load_accounts_for_publish_cache
            from src.utils.startup_profiler import is_page_load_profiler_enabled

            t0 = time.perf_counter() if is_page_load_profiler_enabled() else 0.0
            accounts = await load_accounts_for_publish_cache(force_refresh=True)
            logger.info(f"从数据库加载到 {len(accounts) if accounts else 0} 个账号")
            
            self.available_accounts = accounts or []
            logger.info(f"账号列表加载完毕，共 {len(self.available_accounts)} 个账号")
            if is_page_load_profiler_enabled():
                logging.getLogger("ui.perf").info(
                    "[页面耗时] single page account db refresh: %.0f ms",
                    (time.perf_counter() - t0) * 1000,
                )
            self._apply_accounts_to_ui()
                
        except Exception as e:
            logger.error(f"加载账号列表失败: {e}", exc_info=True)
        finally:
            self._accounts_loading = False
    
    async def _load_accounts_async(self, platform='douyin'):
        """异步加载账号"""
        try:
            accounts = await self.account_manager.get_accounts(platform=platform)  # type: ignore
            
            if not accounts:
                return

            if not hasattr(self, 'available_accounts') or self.available_accounts is None:
                self.available_accounts = []
                
            self.available_accounts.extend(accounts)
            
            # 去重 (根据id)
            seen_ids = set()
            unique_accounts = []
            for acc in self.available_accounts:
                if acc['id'] not in seen_ids:
                    unique_accounts.append(acc)
                    seen_ids.add(acc['id'])
            self.available_accounts = unique_accounts

            if not self.available_accounts:
                self.account_label.setText("无可用发布账号 (请先添加并登录)")
                self.account_label.setStyleSheet(
                    "color: red; font-weight: bold; margin-left: 10px;"
                )
                self.btn_select_account.setEnabled(False)
            else:
                self.btn_select_account.setEnabled(True)
                # 如果当前已选账号不在列表中（可能被删除），则重置
                if self.selected_account and self.selected_account.get('type') == 'account':
                    # 注意：selected_account 结构变化了，这里需要小心
                    # 这里简化处理，只有当 selected_account 是单个账号时才检查
                    current_acc_id = self.selected_account['data'].get('id')
                    exists = any(a['id'] == current_acc_id for a in self.available_accounts)
                    if not exists:
                        self.selected_account = None
                        self._set_account_label_placeholder()
                        self._refresh_account_dependent_settings_ui()

            # 加载完成后更新发布按钮状态
            self._update_publish_button_state()

        except Exception as e:
            logger.error(f"异步加载账号失败 ({platform}): {e}")
            
    @asyncSlot()
    async def _on_select_account(self):
        """选择账号按钮点击槽函数"""
        logger.info("点击选择账号按钮，为保证昵称与状态均同步最新，强制从数据库重新加载账号列表...")
        await self._load_accounts()
        
        if not hasattr(self, 'available_accounts') or not self.available_accounts:
            InfoBar.warning(
                title="暂无账号",
                content="请先在账号管理页面添加并登录账号或确保系统已有最新同步数据",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )
            return
            
        # 异步显示选择弹窗
        logger.info("准备显示账号选择弹窗...")
        await self._async_show_selection_dialog()

    async def _async_show_selection_dialog(self):
        """异步显示选择弹窗（单用户模式：加载本地全部账号组）。使用 show()+Future 替代 exec()，避免阻塞 asyncio 事件循环导致 qasync 报 “Cannot enter into task” 的 reentrancy 错误。"""
        try:
            groups = []
            if hasattr(self, 'group_service'):
                groups = await self.group_service.get_groups(user_id=None)
            
            from src.ui.dialogs.account_selection_dialog import AccountSelectionDialog
            dialog = AccountSelectionDialog(self.window() or self)
            dialog.set_data(self.available_accounts, groups, tags_filter_only=True)
            dialog.setWindowModality(Qt.WindowModality.WindowModal)

            loop = asyncio.get_event_loop()
            future = loop.create_future()

            def on_finished(code: int):
                if future.done():
                    return
                try:
                    r = dialog.get_selected_result() if code == int(QDialog.DialogCode.Accepted) else None
                except Exception as e:
                    future.set_exception(e)
                else:
                    future.set_result(r)

            dialog.finished.connect(on_finished)
            dialog.show()
            result = await future

            if result:
                # 结果可能是 {'type': 'account', 'data': ...} 或 {'type': 'group', 'data': ...}
                rtype = result.get("type")
                data = result.get("data")
                if rtype == "account" and isinstance(data, list):
                    if len(data) == 1:
                        result["data"] = data[0]
                    else:
                        logger.warning(
                            "单任务账号选择：期望单个账号 dict，收到 list（长度=%s），已忽略",
                            len(data),
                        )
                        InfoBar.warning(
                            title="选择异常",
                            content="请重新选择发布对象。",
                            parent=self,
                            position=InfoBarPosition.TOP,
                            duration=4000,
                        )
                        return
                elif rtype == "group" and isinstance(data, list):
                    if len(data) == 1:
                        result["data"] = data[0]
                    else:
                        logger.warning(
                            "单任务账号选择：期望单个账号组 dict，收到 list（长度=%s），已忽略",
                            len(data),
                        )
                        InfoBar.warning(
                            title="选择异常",
                            content="请重新选择发布对象或账号组。",
                            parent=self,
                            position=InfoBarPosition.TOP,
                            duration=4000,
                        )
                        return

                self.selected_account = result
                # 注意：self.selected_account 原本存储的是 account dict, 现在变成了 result dict
                # 后后续使用 self.selected_account 的地方都需要适配

                # 更新显示
                if result['type'] == 'account':
                    account = result['data']
                    platform = account.get('platform', 'unknown')
                    platform_cn = self._get_platform_name_cn(platform)
                    name = account.get('platform_username', '未命名')
                    self.account_label.setText(f"{platform_cn} | {name}")
                    self.account_label.setStyleSheet("margin-left: 10px;")
                elif result['type'] == 'group':
                    group = result['data']
                    name = group.get('group_name', '未命名')
                    count = len(group.get('platforms', []))
                    self.account_label.setText(f"账号组 | {name} ({count}个平台)")
                    self.account_label.setStyleSheet("margin-left: 10px;")
                
                self._update_publish_button_state()
                self._refresh_account_dependent_settings_ui()
                if (
                    not self._is_image_mode
                    and getattr(self, "_auto_match_video_switch", None)
                    and self._auto_match_video_switch.isChecked()
                ):
                    self._schedule_single_auto_video_match()
        except Exception as e:
            logger.error(f"显示账号选择弹窗失败: {e}", exc_info=True)
            InfoBar.error(
                title="错误",
                content=f"加载账号组数据失败: {str(e)}",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )

    def _on_auto_match_video_switch_changed(self, checked: bool) -> None:
        """视频库自动匹配开关：与「添加视频」互斥，并触发一次匹配或清除自动路径。"""
        save_persisted_single_auto_match_video_library(checked)
        if self._is_image_mode:
            return
        if checked:
            self.btn_add_video.setEnabled(False)
            self._schedule_single_auto_video_match()
        else:
            self.btn_add_video.setEnabled(True)
            if getattr(self, "_file_from_auto_library", False):
                self.selected_file_path = ""
                self._file_from_auto_library = False
                if hasattr(self, "file_info_label") and self.file_info_label:
                    self.file_info_label.setText(self._empty_file_hint())
                self._update_preview_video_source("")
            self._update_publish_button_state()

    def _schedule_single_auto_video_match(self) -> None:
        """异步从媒体库匹配一条视频（去抖：快速连点账号/开关时只保留最后一次）。"""
        if self._is_image_mode:
            return
        sw = getattr(self, "_auto_match_video_switch", None)
        if sw is None or not sw.isChecked():
            return
        self._single_auto_apply_generation += 1
        gen = self._single_auto_apply_generation

        async def _run() -> None:
            try:
                await self._apply_auto_video_from_library(gen)
            except Exception as e:
                logger.error("单视频自动匹配失败: %s", e, exc_info=True)
                if gen == self._single_auto_apply_generation:
                    self._show_single_auto_shortage_dialog(f"自动匹配异常：{e}")

        self._create_tracked_task(
            _run(),
            name="ui.single_publish.auto_video_match",
        )

    def _selection_to_matcher_account(self) -> Optional[Dict[str, Any]]:
        """将当前「选择账号」弹窗结果转为 MaterialAutoMatcher 使用的账号/组结构。"""
        sel = self.selected_account
        if not sel or not isinstance(sel, dict):
            return None
        if sel.get("type") == "account":
            data = sel.get("data")
            if not isinstance(data, dict):
                return None
            return dict(data)
        if sel.get("type") == "group":
            g = sel.get("data")
            if not isinstance(g, dict):
                return None
            gid = g.get("id")
            gname = (g.get("group_name") or "").strip() or "未命名账号组"
            return {
                "id": f"group:{gid}",
                "_type": "group",
                "group_id": gid,
                "group_name": gname,
                "platform": "account_group",
                "platform_username": gname,
                "_group_data": g,
            }
        return None

    async def _load_exclude_paths_for_single_selection(self) -> set:
        """发布列表中待发布/进行中任务已占用的素材路径，避免自动匹配重复。"""
        try:
            from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync

            sel = self.selected_account
            if not sel or not isinstance(sel, dict):
                return set()
            repo = PublishRecordRepositoryAsync()
            account_ids: List[int] = []
            if sel.get("type") == "account":
                data = sel.get("data")
                if isinstance(data, dict):
                    aid = data.get("id")
                    if isinstance(aid, int):
                        account_ids.append(aid)
            elif sel.get("type") == "group":
                g = sel.get("data")
                if isinstance(g, dict):
                    for m in g.get("accounts") or []:
                        aid = m.get("id") if isinstance(m, dict) else None
                        if isinstance(aid, int):
                            account_ids.append(aid)
            if not account_ids:
                return set()
            return await repo.get_active_file_paths_for_accounts(self.user_id, account_ids)
        except Exception as e:
            logger.warning("查询发布列表已占用素材路径失败: %s", e, exc_info=True)
            return set()

    async def _apply_auto_video_from_library(self, generation: int) -> None:
        """从当前所选主体媒体库「视频/未发布」按文件名顺序取 1 条（与批量自动匹配一致）。"""
        if generation != self._single_auto_apply_generation:
            return
        if self._is_image_mode:
            return
        sw = getattr(self, "_auto_match_video_switch", None)
        if sw is None or not sw.isChecked():
            return
        if not self.selected_account:
            if getattr(self, "_file_from_auto_library", False):
                self.selected_file_path = ""
                self._file_from_auto_library = False
            if hasattr(self, "file_info_label") and self.file_info_label:
                self.file_info_label.setText("请先选择发布对象后再使用视频库自动匹配")
            self._update_preview_video_source("")
            self._update_publish_button_state()
            return

        acc = self._selection_to_matcher_account()
        if not acc:
            return

        from src.pro_features.batch.services.material_auto_matcher import MaterialAutoMatcher

        matcher = MaterialAutoMatcher(media_type="video")
        exclude = await self._load_exclude_paths_for_single_selection()
        matcher.set_exclude_paths(exclude)
        matched, shortage = matcher.fetch_materials(acc, 1, None)

        if generation != self._single_auto_apply_generation:
            return

        if shortage or not matched:
            self.selected_file_path = ""
            self._file_from_auto_library = False
            if hasattr(self, "file_info_label") and self.file_info_label:
                self.file_info_label.setText(self._empty_file_hint())
            self._update_preview_video_source("")
            self._update_publish_button_state()
            self._show_single_auto_shortage_dialog(shortage or "未能从媒体库匹配到可用视频")
            return

        m0 = matched[0]
        fp = m0.get("file_path") or ""
        self.selected_file_path = fp
        self._file_from_auto_library = True
        if hasattr(self, "file_info_label") and self.file_info_label:
            try:
                size_mb = os.path.getsize(fp) / (1024 * 1024)
            except OSError:
                size_mb = 0.0
            self.file_info_label.setText(
                f"{os.path.basename(fp)} | 大小: {size_mb:.2f} MB（视频库自动匹配）"
            )
        self._update_preview_video_source(fp)
        self._update_publish_button_state()
        self._schedule_apply_copywriting_from_library()

    def _show_single_auto_shortage_dialog(self, message: str) -> None:
        from src.ui.components.base_dialog import AppMessageBoxBase

        parent = self.window() or self
        w = AppMessageBoxBase(parent, header_title="素材不足")
        body = BodyLabel((message or "").strip() or "请先在媒体库中为对应账号分配视频。", w)
        body.setWordWrap(True)
        w.viewLayout.addWidget(body)
        w.widget.setMinimumWidth(420)
        w.yesButton.setText("确定")
        w.cancelButton.setVisible(False)
        button_layout = getattr(w, "buttonLayout", None)
        if button_layout is None:
            button_layout = w.buttonGroup.layout()
        if button_layout:
            button_layout.removeWidget(w.cancelButton)
            button_layout.removeWidget(w.yesButton)
            button_layout.addWidget(w.yesButton)
        w.exec()

    def _on_copywriting_auto_switch_changed(self, checked: bool) -> None:
        """自动匹配总开关。"""
        save_persisted_single_auto_match_copywriting(checked)
        self._update_copywriting_ui_visibility()
        if checked:
            self._schedule_apply_copywriting_from_library()

    def _on_copywriting_mode_changed(self, index: int):
        """文案匹配模式变更。"""
        mode = self._copywriting_mode_combo.itemData(index) or CopywritingMatchMode.STANDARD
        save_persisted_single_copywriting_match_mode(mode)
        self._update_copywriting_ui_visibility()
        if self._copywriting_auto_switch.isChecked():  # type: ignore
            self._schedule_apply_copywriting_from_library()

    def _on_copywriting_category_changed(self, index: int):
        """随机分类变更。"""
        cat_id = self._copywriting_category_combo.itemData(index)
        save_persisted_single_copywriting_random_category(cat_id)
        if self._copywriting_auto_switch.isChecked():  # type: ignore
            self._schedule_apply_copywriting_from_library()

    def _get_current_copywriting_mode(self) -> str:
        """安全获取当前文案匹配模式。
        
        ComboBox 被 setVisible(False) 隐藏后，currentData() 可能返回 None。
        此方法优先读取控件值，若为 None 则回退到持久化配置，确保始终返回有效的模式字符串。
        """
        combo = getattr(self, "_copywriting_mode_combo", None)
        if combo is not None:
            data = combo.currentData()
            if data is not None:
                return str(data)
            # ComboBox 隐藏时 currentData() 返回 None，改用 currentIndex 查找
            idx = combo.currentIndex()
            if idx >= 0:
                item_data = combo.itemData(idx)
                if item_data is not None:
                    return str(item_data)
        # 最终兜底：从持久化配置读取
        return load_persisted_single_copywriting_match_mode()

    def _update_copywriting_ui_visibility(self):
        """根据开关和模式显示/隐藏下拉框。"""
        sw = getattr(self, "_copywriting_auto_switch", None)
        if sw is None:
            return
        checked = sw.isChecked()
        self._copywriting_mode_combo.setVisible(checked)
        
        # 注意：setVisible(False) 后 currentData() 可能返回 None，
        # 用 _get_current_copywriting_mode() 读取模式，避免此问题
        mode = self._get_current_copywriting_mode()
        self._copywriting_category_combo.setVisible(checked and mode == CopywritingMatchMode.RANDOM_CATEGORY)

    @asyncSlot()
    async def _refresh_copywriting_categories_async(self):
        """异步加载随机文案分类列表。"""
        if not hasattr(self, "_copywriting_category_combo"):
            return
        try:
            from src.infrastructure.storage.repositories.random_copywriting_repository import RandomCopywritingRepository
            cats = await RandomCopywritingRepository.list_categories()
            
            self._copywriting_category_combo.blockSignals(True)
            self._copywriting_category_combo.clear()
            self._copywriting_category_combo.addItem("选择分类...", userData=None)
            
            saved_cat_id = load_persisted_single_copywriting_random_category()
            target_idx = 0
            
            for i, cat in enumerate(cats, start=1):
                self._copywriting_category_combo.addItem(cat["name"], userData=cat["id"])
                if cat["id"] == saved_cat_id:
                    target_idx = i

            _cat_cb = self._copywriting_category_combo
            _cat_fm = QFontMetrics(self.font())
            _cat_w = max(_cat_fm.horizontalAdvance(_cat_cb.itemText(i)) for i in range(_cat_cb.count()))
            _cat_cb.setMinimumWidth(max(160, _cat_w + 44))

            self._copywriting_category_combo.setCurrentIndex(target_idx)
            self._copywriting_category_combo.blockSignals(False)
        except Exception as e:
            logger.warning("加载随机文案分类失败: %s", e)
            InfoBar.warning(
                "加载分类失败",
                "随机文案分类读取失败，请稍后重试或检查文案库。",
                parent=self.window() or self,
                position=InfoBarPosition.TOP,
                duration=3500,
            )

    def _schedule_apply_copywriting_from_library(self) -> None:
        if self._is_image_mode:
            return
        sw = getattr(self, "_copywriting_auto_switch", None)
        if sw is None or not sw.isChecked():
            return
        fp = (self.selected_file_path or "").strip()
        if not fp:
            return
        self._copywriting_auto_apply_generation += 1
        gen = self._copywriting_auto_apply_generation

        async def _run() -> None:
            try:
                await self._apply_copywriting_from_library_async(gen)
            except Exception as e:
                logger.error("单视频标准文案库自动匹配失败: %s", e, exc_info=True)
                if gen == self._copywriting_auto_apply_generation:
                    InfoBar.error(
                        title="匹配失败",
                        content=str(e),
                        parent=self.window() or self,
                        position=InfoBarPosition.TOP,
                        duration=4000,
                    )

        self._create_tracked_task(
            _run(),
            name="ui.single_publish.auto_copywriting",
        )

    async def _apply_copywriting_from_library_async(self, generation: int) -> None:
        if generation != self._copywriting_auto_apply_generation:
            return
        sw = getattr(self, "_copywriting_auto_switch", None)
        if sw is None or not sw.isChecked():
            return
        
        # 即使是图文模式，如果开启了匹配，也可以使用随机库（标准库仍依赖文件名，对图文通常不生效）
        raw_fp = (self.selected_file_path or "").strip().split(",")[0].strip()
        
        # 注意：ComboBox 隐藏时 currentData() 可能返回 None，用 _get_current_copywriting_mode() 兜底
        mode = self._get_current_copywriting_mode()
        cat_id = self._copywriting_category_combo.currentData()

        if mode == CopywritingMatchMode.RANDOM_CATEGORY and cat_id is None:
            InfoBar.warning(
                "请选择分类",
                "当前为随机(分类)模式，请先选择一个随机文案分类。",
                parent=self.window() or self,
                position=InfoBarPosition.TOP,
                duration=3500,
            )
            return

        logger.debug("文案自动匹配开始: mode=%s, file_path=%s, cat_id=%s", mode, raw_fp, cat_id)

        # 标准库：提前校验文件名是否含有效作品编号，给出更友好的提示
        if mode == CopywritingMatchMode.STANDARD:
            from src.pro_features.batch.copywriting_helpers import extract_work_id_from_filename
            work_id = extract_work_id_from_filename(raw_fp) or extract_work_id_from_filename(os.path.basename(raw_fp))
            if not work_id:
                logger.debug("文件名中未找到作品编号（格式 A0001），跳过标准库匹配: %s", raw_fp)
                if raw_fp:
                    InfoBar.warning(
                        "无法匹配文案",
                        f"文件名「{os.path.basename(raw_fp)}」不含作品编号（格式：A0001），标准库无法匹配。",
                        parent=self.window() or self,
                        position=InfoBarPosition.TOP,
                        duration=4000,
                    )
                return

        # 调用统一匹配服务
        result = await CopywritingMatchService.match(
            mode=mode,
            file_path=raw_fp,
            category_id=cat_id,
            apply_all=False,  # 单任务页不使用统一文案覆盖，直接填充
            use_lib_title=True,
            use_lib_desc=True,
        )

        logger.debug("文案匹配结果: result=%s", result)

        if generation != self._copywriting_auto_apply_generation:
            return

        if not result:
            # 未匹配到文案时，清空当前简介，避免保留上次匹配/手填内容造成误用。
            if hasattr(self, "desc_edit") and self.desc_edit:
                self.desc_edit.setPlainText("")
            ctl = getattr(self, "_work_desc_controller", None)
            if ctl is not None:
                ctl.refresh()

            # 根据模式给出不同的提示
            if mode == CopywritingMatchMode.STANDARD:
                from src.pro_features.batch.copywriting_helpers import extract_work_id_from_filename
                work_id = extract_work_id_from_filename(raw_fp) or extract_work_id_from_filename(os.path.basename(raw_fp))
                if work_id:
                    InfoBar.warning(
                        "未匹配到文案",
                        f"标准文案库中不存在作品编号「{work_id}」对应条目，请先导入标准文案库。",
                        parent=self.window() or self,
                        position=InfoBarPosition.TOP,
                        duration=4000,
                    )
            elif mode in (CopywritingMatchMode.RANDOM_ALL, CopywritingMatchMode.RANDOM_CATEGORY):
                # 随机库匹配失败（库中无数据），给出提示
                hint = "指定分类" if mode == CopywritingMatchMode.RANDOM_CATEGORY else "全库"
                InfoBar.warning(
                    "随机库无可用文案",
                    f"随机文案库（{hint}）中暂无文案，请先前往「文案库管理」添加随机库文案。",
                    parent=self.window() or self,
                    position=InfoBarPosition.TOP,
                    duration=4000,
                )
            return

        title = result.get("title", "")
        desc = result.get("description", "")

        logger.debug("文案匹配填充: title=%r, desc=%r", title, desc)

        if hasattr(self, "title_edit") and self.title_edit:
            self.title_edit.setText(title)
        if hasattr(self, "desc_edit") and self.desc_edit:
            self.desc_edit.setPlainText(desc)
        
        ctl = getattr(self, "_work_desc_controller", None)
        if ctl is not None:
            ctl.refresh()


    @staticmethod
    def _get_platform_name_cn(platform: str) -> str:
        """获取平台中文名称"""
        from src.utils.platform_names import get_platform_display_name
        return get_platform_display_name(platform)

    @staticmethod
    def _parse_optional_account_id(raw: Any) -> Optional[int]:
        if raw is None:
            return None
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.strip().isdigit():
            return int(raw.strip())
        return None

    def _find_account_in_available(
        self, record: Dict[str, Any], accounts: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """在已加载的账号列表中匹配发布记录对应账号（仅是否存在，不校验登录态）。"""
        if not accounts:
            return None
        aid = self._parse_optional_account_id(record.get("platform_account_id"))
        if aid is not None:
            for acc in accounts:
                raw_id = acc.get("id")
                try:
                    if raw_id is not None and int(raw_id) == aid:
                        return acc
                except (TypeError, ValueError):
                    continue
        tp = (record.get("platform") or "").strip()
        tn = (record.get("platform_username") or "").strip()
        if tp and tn:
            for acc in accounts:
                if (acc.get("platform") or "").strip() == tp and (
                    acc.get("platform_username") or ""
                ).strip() == tn:
                    return acc
        return None

    def _apply_account_label_for_found(self, record: Dict[str, Any], found_account: Dict[str, Any]) -> None:
        if not hasattr(self, "account_label") or not self.account_label:
            return
        platform_cn = self._get_platform_name_cn(
            (found_account.get("platform") or record.get("platform") or "").strip()
        )
        name = (found_account.get("platform_username") or "").strip() or "未命名"
        self.account_label.setText(f"{platform_cn} | {name}")
        self.account_label.setStyleSheet("margin-left: 10px;")

    def _apply_account_label_missing_in_library(self, record: Dict[str, Any]) -> None:
        if not hasattr(self, "account_label") or not self.account_label:
            self.selected_account = None
            return
        platform_cn = self._get_platform_name_cn((record.get("platform") or "").strip())
        tn = (record.get("platform_username") or "").strip()
        if tn:
            self.account_label.setText(f"{platform_cn} | {tn}（账号库中无此账号）")
        else:
            self._set_account_label_placeholder()
        self.selected_account = None
        self._refresh_account_dependent_settings_ui()

    async def _deferred_bind_publish_record_account(self, record: Dict[str, Any], bind_gen: int) -> None:
        """账号列表尚未就绪或需按 ID 补查时，异步加载后再绑定（避免误报「不存在」）。"""
        try:
            if bind_gen != self._account_bind_generation:
                return
            await self._load_accounts()
            if bind_gen != self._account_bind_generation:
                return
            accounts = list(getattr(self, "available_accounts", None) or [])
            found = self._find_account_in_available(record, accounts)
            if not found and self.account_manager:
                aid = self._parse_optional_account_id(record.get("platform_account_id"))
                if aid is not None:
                    try:
                        acc = await self.account_manager.get_account_by_id(aid)
                    except Exception:
                        acc = None
                    if acc:
                        found = acc
                        if not any(a.get("id") == acc.get("id") for a in accounts):
                            self.available_accounts = accounts + [acc]
            if bind_gen != self._account_bind_generation:
                return
            if found:
                self.selected_account = {"type": "account", "data": found}
                self._apply_account_label_for_found(record, found)
            else:
                self._apply_account_label_missing_in_library(record)
            self._update_publish_button_state()
            # 控件已在 set_publish_data 中按记录填过，此处只切换堆叠页到当前账号平台
            self._refresh_account_dependent_settings_ui(sync_work_declaration_from_storage=False)
        except Exception as e:
            logger.error("异步回填发布账号失败: %s", e, exc_info=True)
    
    def _on_browse_file(self):
        """浏览文件（视频单文件；图文可多选，路径英文逗号拼接）"""
        if (
            not self._is_image_mode
            and getattr(self, "_auto_match_video_switch", None)
            and self._auto_match_video_switch.isChecked()
        ):
            return
        if self._is_image_mode:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                "选择图片文件",
                "",
                "图片文件 (*.jpg *.jpeg *.png *.webp *.gif *.bmp);;所有文件 (*.*)",
            )
            if not paths:
                return
            self.selected_file_path = ",".join(paths)
            self._set_file_info_label_for_paths(paths)
            self._update_publish_button_state()
            self._create_tracked_task(
                self._load_thumbnail_async(self.selected_file_path),
                name="ui.single_publish.load_thumbnail",
            )
            return

        start_dir = get_last_video_import_directory()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择视频文件",
            start_dir,
            "视频文件 (*.mp4 *.avi *.mov *.mkv *.wmv);;所有文件 (*.*)",
        )

        if file_path:
            save_last_video_import_directory_from_path(file_path)
            self.selected_file_path = file_path
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)
            size_mb = file_size / (1024 * 1024)
            self.file_info_label.setText(f"{file_name} | 大小: {size_mb:.2f} MB")
            self._update_publish_button_state()
            self._update_preview_video_source(file_path)
            self._schedule_apply_copywriting_from_library()

    def _on_browse_image_folder(self):
        """选择文件夹，自动读取其中所有图片文件（按文件名排序）。"""
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹", "")
        if not folder:
            return
        image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
        paths = sorted(
            [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if os.path.isfile(os.path.join(folder, f))
                and os.path.splitext(f)[1].lower() in image_exts
            ]
        )
        if not paths:
            InfoBar.warning(
                title="未找到图片",
                content=f"所选文件夹中没有支持的图片文件（jpg/jpeg/png/webp/gif/bmp）",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return
        marker = f"{_FOLDER_MARKER_PREFIX}{folder}"
        self.selected_file_path = marker + "," + ",".join(paths)
        self._set_file_info_label_for_paths(paths)
        self._update_publish_button_state()
        self._create_tracked_task(
            self._load_thumbnail_async(self.selected_file_path),
            name="ui.single_publish.load_thumbnail",
        )

    async def _load_thumbnail_async(self, file_path: str, *, prefer_image: bool = False):
        """异步加载预览图：仅图文页有 preview_label，按路径读图片字节（视频预览由 VideoWidget 负责）。"""
        try:
            if getattr(self, "preview_label", None) is None:
                return
            loop = asyncio.get_running_loop()
            preview_path = self._resolve_preview_path(file_path)
            if not preview_path:
                return

            load_as_image = (
                self._is_image_mode
                or prefer_image
                or self._path_looks_like_image(preview_path)
            )
            if not load_as_image:
                return

            def _read_image_bytes() -> Optional[bytes]:
                try:
                    with open(preview_path, "rb") as f:
                        return f.read()
                except OSError as e:
                    logger.warning("读取图片预览失败: %s", e)
                    return None

            img_data = await loop.run_in_executor(None, _read_image_bytes)
            if img_data:
                self._schedule_base_page_timer(
                    "preview_thumbnail_apply",
                    0,
                    lambda img_data=img_data: self._update_preview_from_data(img_data),
                )
        except Exception as e:
            logger.error(f"加载缩略图失败: {e}")

    def _update_preview_from_data(self, image_data: bytes):
        """从图片字节更新预览图（主线程调用，兼容打包环境）"""
        pixmap = QPixmap()
        if not pixmap.loadFromData(image_data):
            return
        self._apply_preview_pixmap(pixmap)

    def _update_preview(self, image_path: str):
        """更新预览图（高清适配版本），支持传入文件路径"""
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return
        self._apply_preview_pixmap(pixmap)

    def _apply_preview_pixmap(self, pixmap: QPixmap):
        """将缩放后的 pixmap 应用到预览标签（高清适配）"""
        if pixmap.isNull():
            return
        if not hasattr(self, 'preview_label') or self.preview_label is None:
            return
        ratio = self.devicePixelRatio()
        target_w = int(280 * ratio)
        target_h = int(280 * ratio)
        scaled_pixmap = pixmap.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)  # type: ignore
        scaled_pixmap.setDevicePixelRatio(ratio)
        self.preview_label.setStyleSheet("background-color: transparent; border: none; border-radius: 12px;")
        self.preview_label.setPixmap(scaled_pixmap)
        self.preview_label.setText("")

    def _on_browse_cover(self):
        """浏览封面"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择封面图片",
            "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp);;所有文件 (*.*)"
        )
        
        if file_path:
            import os
            self.selected_cover_path = file_path
            self.cover_path_label.setText(os.path.basename(file_path))

    def _on_cover_type_changed(self, _index: int = 0) -> None:
        """封面类型下拉变更：本地封面时启用「选择」按钮。"""
        is_local_cover = self._cover_type_is_local()
        self.btn_browse_cover.setEnabled(is_local_cover)

        if not is_local_cover:
            self.selected_cover_path = ""
            self.cover_path_label.setText("未选择本地封面")
        else:
            if not getattr(self, "selected_cover_path", ""):
                self.cover_path_label.setText("请选择封面图片")
            else:
                import os

                self.cover_path_label.setText(os.path.basename(self.selected_cover_path))
    
    def _update_publish_button_state(self):
        """更新发布按钮状态"""
        if not hasattr(self, 'btn_publish') or self.btn_publish is None:
            return
        has_file = bool(self.selected_file_path)
        has_account = self.selected_account is not None
        self.btn_publish.setEnabled(has_file and has_account)
    
    def _refresh_user_id(self):
        """从 CurrentUserService 刷新 user_id（登录后调用）"""
        self.user_id = self._current_user_svc.get_user_id_or_default(1)
        if self.account_manager and hasattr(self.account_manager, 'user_id'):
            self.account_manager.user_id = self.user_id

    def _on_publish(self):
        return self._creation_controller.publish()

    def _on_publish_legacy(self):
        """添加到发布列表（操作前需登录）"""
        if not self._current_user_svc.is_logged_in():
            try:
                from src.ui.dialogs.login_dialog import LoginDialog
                from qfluentwidgets import InfoBar, InfoBarPosition
                dialog = LoginDialog(self)
                dialog.login_success.connect(self._refresh_user_id)
                if not dialog.exec():
                    InfoBar.warning("请先登录", "发布前需要登录", parent=self, position=InfoBarPosition.TOP)
                    return
                self._refresh_user_id()
            except Exception as e:
                from qfluentwidgets import InfoBar, InfoBarPosition
                InfoBar.warning("请先登录", "发布前需要登录", parent=self, position=InfoBarPosition.TOP)
                return
        if not self.selected_file_path:
            from src.ui.utils.fluent_dialogs import show_warning
            msg = "请先选择图片文件" if self._is_image_mode else "请先选择视频文件"
            show_warning(self, "错误", msg)
            return

        if self._is_image_mode:
            paths = _split_comma_paths(self.selected_file_path)
            missing = [p for p in paths if not os.path.exists(p)]
            if missing:
                from src.ui.utils.fluent_dialogs import show_warning
                show_warning(
                    self,
                    "错误",
                    "部分图片路径无效或文件不存在，请重新选择：\n"
                    + "\n".join(missing[:5])
                    + ("…" if len(missing) > 5 else ""),
                )
                return
        else:
            if not os.path.exists(self.selected_file_path):
                from src.ui.utils.fluent_dialogs import show_warning
                show_warning(self, "错误", "视频文件不存在，请重新选择")
                return
        
        if not self.selected_account:
            from src.ui.utils.fluent_dialogs import show_warning
            show_warning(self, "错误", "请选择发布对象")
            return
            
        target_accounts = []
        if self.selected_account['type'] == 'account':
            target_accounts.append(self.selected_account['data'])
        elif self.selected_account['type'] == 'group':
            # 过滤掉无效账号（如未登录？目前仅获取列表，暂不过滤状态，由发布服务处理或提示）
            # 注意：group 数据里的 accounts 可能只包含基本信息，如果需要完整信息可能需要再查询
            # 但 _execute_add_to_list 里似乎只需要 account id 和 platform 等基本信息
            target_accounts.extend(self.selected_account['data'].get('accounts', []))
            
        if not target_accounts:
            from src.ui.utils.fluent_dialogs import show_warning
            show_warning(self, "错误", "所选账号组为空")
            return

        # 视频号图文发布必须填写作品标题
        if self._is_image_mode:
            _has_wechat = any(
                (acc.get("platform") or "").strip() == "wechat_video"
                for acc in target_accounts
            )
            if _has_wechat:
                _title_edit = getattr(self, "title_edit", None)
                _title_text = _title_edit.text().strip() if _title_edit else ""
                if not _title_text:
                    from qfluentwidgets import InfoBar, InfoBarPosition
                    InfoBar.warning(
                        "作品标题必填",
                        "所选发布对象包含视频号账号，图文发布必须填写「作品标题」，"
                        "请在「作品描述」区域填写标题后再生成任务。",
                        parent=self,
                        position=InfoBarPosition.TOP,
                        duration=6000,
                    )
                    return

        # Pro 平台必须先登录才可使用
        from src.utils.pro_platforms import is_pro_platform
        has_pro_platform = any(is_pro_platform(acc.get("platform", "")) for acc in target_accounts)
        if has_pro_platform and not self._current_user_svc.is_logged_in():
            try:
                from src.ui.dialogs.login_dialog import LoginDialog
                from qfluentwidgets import InfoBar
                dialog = LoginDialog(self)
                dialog.login_success.connect(self._refresh_user_id)
                if not dialog.exec():
                    InfoBar.warning("请先登录", "使用 Pro 平台需要先登录", parent=self)
                    return
                self._refresh_user_id()
            except Exception as e:
                from qfluentwidgets import InfoBar
                InfoBar.warning("请先登录", "使用 Pro 平台需要先登录", parent=self)
                return
        if has_pro_platform and not self._current_user_svc.has_pro_permission():
            from qfluentwidgets import InfoBar
            InfoBar.warning("需要 Pro 会员", "所选平台需要 Pro 会员，请升级/续费", parent=self)
            return
        
        # 获取发布信息：描述=全文（含 #话题）；话题仅从描述中解析（#关键词 后跟空格才确认，与抖音一致）；标题不再用文件名回填
        title = (self.title_edit.text() or "").strip()
        description = self.desc_edit.toPlainText() if hasattr(self.desc_edit, 'toPlainText') else getattr(self.desc_edit, 'text', lambda: "")()
        tags = parse_topic_list(description)

        from src.ui.pages.publish.publish_validators import wechat_video_short_title_validation_error
        for acc in target_accounts:
            err = wechat_video_short_title_validation_error(acc.get("platform", ""), title)
            if err:
                self._on_publish_error(err)
                return
        
        norm_edit_id = normalize_publish_record_id(self.editing_record_id)
        if norm_edit_id is not None and len(target_accounts) > 1:
            from src.ui.utils.fluent_dialogs import show_warning
            show_warning(
                self,
                "提示",
                "正在编辑已有任务时仅支持选择单个发布账号。\n请改选单个账号，或不要选择账号组后再保存。",
            )
            self.status_label.setText("准备就绪")
            return

        # 更新状态
        self.status_label.setText(f"正在提交 {len(target_accounts)} 个任务...")
        self.btn_publish.setEnabled(False)

        # 编辑 ID 必须在调度协程前固定下来：多协程并发时若先执行的任务清空 self.editing_record_id，后续会误走新建
        self._create_tracked_task(
            self._dispatch_add_to_list_after_duplicate_guard(
                target_accounts,
                norm_edit_id,
                title,
                description,
                tags,
            ),
            name="ui.single_publish.dispatch_add_to_list",
        )

    async def _dispatch_add_to_list_after_duplicate_guard(
        self,
        target_accounts: List[Dict[str, Any]],
        norm_edit_id: Optional[int],
        title: str,
        description: str,
        tags: List[str],
    ) -> None:
        """按「素材路径+平台+账号」过滤发布列表中待发布/进行中的重复项后再派发添加（视频/图文）。"""
        from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
        from src.ui.pages.publish.publish_duplicate_guard import filter_accounts_for_new_publish_task
        from src.ui.utils.fluent_dialogs import show_warning

        media_ft = "image" if self._is_image_mode else "video"
        media_zh = "图文" if self._is_image_mode else "视频"
        repo = PublishRecordRepositoryAsync()
        valid, skip_lines = await filter_accounts_for_new_publish_task(
            repo,
            self.user_id,
            self.selected_file_path,
            target_accounts,
            file_type=media_ft,
            exclude_record_id=norm_edit_id,
        )
        if skip_lines:
            show_warning(
                self,
                "部分账号无法添加",
                f"以下账号在发布列表中已有相同{media_zh}任务（待发布或进行中），已跳过：\n\n"
                + "\n".join(skip_lines),
            )
        if not valid:
            self.status_label.setText("准备就绪")
            self.btn_publish.setEnabled(True)
            return
        accounts_to_use = valid

        # 确定任务源：
        # 编辑模式下，若原任务源为账号组（group），且用户未更换素材文件，则保留 group 标记；
        # 只有用户主动更换了视频（或图文的图片/文件夹），才允许将任务源改为 account。
        _sel_type = (self.selected_account or {}).get("type", "account")
        _orig_task_source = getattr(self, "_editing_record_original_task_source", None)
        _orig_file_path = getattr(self, "_editing_record_original_file_path", None) or ""
        _file_changed = (self.selected_file_path or "") != _orig_file_path
        if norm_edit_id is not None and _orig_task_source == "group" and not _file_changed:
            # 编辑账号组任务且未更换素材：强制保留 group 任务源
            _task_source = "group"
        else:
            _task_source = "group" if _sel_type == "group" else "account"

        for i, account_data in enumerate(accounts_to_use):
            edit_rid = norm_edit_id if i == 0 else None
            self._create_tracked_task(
                self._execute_add_to_list(
                    account=account_data,
                    file_path=self.selected_file_path,
                    title=title,
                    description=description,
                    tags=tags,
                    editing_record_id=edit_rid,
                    task_source=_task_source,
                ),
                name="ui.single_publish.execute_add_to_list",
            )

    async def _execute_add_to_list(
        self,
        account: dict,
        file_path: str,
        title: str,
        description: str,
        tags: List[str],
        editing_record_id: Optional[int] = None,
        task_source: Optional[str] = None,
    ):
        """执行添加到列表（使用 PublishRecordRepositoryAsync）"""
        try:
            from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
            publish_repo = PublishRecordRepositoryAsync()
            
            # 格式化标签字符串
            tags_str = ",".join(tags) if tags else ""
            
            # 获取定时发布时间
            scheduled_time = None
            is_schedule = False
            
            if hasattr(self, 'radio_schedule'):
                is_schedule = self.radio_schedule.isChecked()
            elif hasattr(self, 'schedule_checkbox'):
                is_schedule = self.schedule_checkbox.isChecked()
                
            if is_schedule:
                if self.time_picker.time.isValid():  # type: ignore
                    # 已修改时间
                    dt = QDateTime(
                        self.date_picker.date, self.time_picker.time  # type: ignore
                    )
                    scheduled_time = dt.toString("yyyy-MM-dd HH:mm")  # st_str 格式

            # 获取封面路径
            cover_path = None
            if self._cover_type_is_local():
                cover_path = getattr(self, 'selected_cover_path', None)
            
            plat = (account.get("platform") or "").strip()
            preserve_micro = ""
            if editing_record_id is not None:
                preserve_micro = (
                    getattr(self, "_preserve_micro_app_info", "") or ""
                ).strip()
            more_card = getattr(self, "_more_publish_settings_card", None)
            if more_card is None:
                raise RuntimeError("更多发布设置卡片未初始化")
            ext = more_card.build_publish_extension_payload(
                account_platform=plat,
                preserve_micro_app_info=preserve_micro,
            )
            poi_info = ext.poi_info
            wx_loc_pick = ext.wechat_empty_location_open_picker
            micro_app_info = ext.micro_app_info
            cart_info = ext.cart_info
            anchor_info = ext.anchor_info
            privacy_settings = ext.privacy_settings
            music_info = ext.music_info

            ft = "image" if self._is_image_mode else "video"
            orig_status = (
                getattr(self, "_editing_record_original_status", None)
                if editing_record_id is not None
                else None
            )
            msg_base = await add_or_update_publish_record(
                user_id=self.user_id,
                editing_record_id=editing_record_id,
                editing_record_original_status=orig_status,
                account=account,
                file_path=file_path,
                file_type=ft,
                title=title,
                description=description,
                tags_str=tags_str,
                scheduled_time=scheduled_time,
                cover_path=cover_path,
                poi_info=poi_info,
                wechat_empty_location_open_picker=wx_loc_pick,
                micro_app_info=micro_app_info,
                cart_info=cart_info,
                anchor_info=anchor_info,
                privacy_settings=privacy_settings,
                publish_repo=publish_repo,
                music_info=music_info,
                task_source=task_source,
            )
            msg = msg_base
            if scheduled_time:
                msg += f" (定时: {scheduled_time})"

            # 仅在本条为「更新已有记录」时清除编辑态，避免多账号批量新建时误清
            if editing_record_id is not None:
                self.editing_record_id = None
                self._editing_record_original_status = None
                self._editing_record_original_task_source = None
                self._editing_record_original_file_path = None
                self._preserve_micro_app_info = ""
                if hasattr(self, "btn_publish") and self.btn_publish:
                    self.btn_publish.setText("添加到发布列表")

            self._on_publish_success(msg)
                
        except Exception as e:
            logger.error(f"添加到发布列表失败: {e}", exc_info=True)
            self._on_publish_error(str(e))
    
    def _clear_form_after_add(self):
        """添加到发布列表成功后清空任务内容，便于继续添加新任务（保留账号选择）。"""
        self.selected_file_path = ""
        self.editing_record_id = None
        self._editing_record_original_status = None
        self._editing_record_original_task_source = None
        self._editing_record_original_file_path = None
        self._publish_edit_return_route = None
        if hasattr(self, "file_info_label") and self.file_info_label:
            self.file_info_label.setText(self._empty_file_hint())
        if hasattr(self, "preview_label") and self.preview_label:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(self._preview_placeholder_text())
            self._apply_preview_placeholder_style()
        self._update_preview_video_source("")
        if hasattr(self, "title_edit") and self.title_edit:
            self.title_edit.clear()
        if hasattr(self, "desc_edit") and self.desc_edit:
            self.desc_edit.setPlainText("")
        self.selected_cover_path = ""
        self._set_cover_type_combo(_COVER_TYPE_FIRST_FRAME)
        if hasattr(self, "cover_path_label") and self.cover_path_label:
            self.cover_path_label.setText("未选择本地封面")
        self._preserve_micro_app_info = ""
        more_card = getattr(self, "_more_publish_settings_card", None)
        if more_card is not None:
            more_card.reset_to_defaults()
        if hasattr(self, "status_label") and self.status_label:
            self.status_label.setText("准备就绪")
        if hasattr(self, "btn_publish") and self.btn_publish:
            self.btn_publish.setText("添加到发布列表")
        if hasattr(self, "btn_return_to_publish") and self.btn_return_to_publish:
            self.btn_return_to_publish.setVisible(False)
        self._refresh_account_dependent_settings_ui()
        self._update_publish_button_state()

    def _reset_form_to_new_page(self):
        """保存并返回列表后，将表单重置为全新页面状态（所有内容未设置，含账号）。"""
        self.selected_account = None
        self.selected_file_path = ""
        self._file_from_auto_library = False
        self.editing_record_id = None
        self._editing_record_original_status = None
        self._editing_record_original_task_source = None
        self._editing_record_original_file_path = None
        self._publish_edit_return_route = None
        if hasattr(self, "account_label") and self.account_label:
            self._set_account_label_placeholder()
        if hasattr(self, "file_info_label") and self.file_info_label:
            self.file_info_label.setText(self._empty_file_hint())
        if hasattr(self, "preview_label") and self.preview_label:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(self._preview_placeholder_text())
            self._apply_preview_placeholder_style()
        self._update_preview_video_source("")
        if hasattr(self, "title_edit") and self.title_edit:
            self.title_edit.clear()
        if hasattr(self, "desc_edit") and self.desc_edit:
            self.desc_edit.setPlainText("")
        self.selected_cover_path = ""
        self._set_cover_type_combo(_COVER_TYPE_FIRST_FRAME)
        if hasattr(self, "cover_path_label") and self.cover_path_label:
            self.cover_path_label.setText("未选择本地封面")
        self._preserve_micro_app_info = ""
        more_card = getattr(self, "_more_publish_settings_card", None)
        if more_card is not None:
            more_card.reset_to_defaults()
        if hasattr(self, "radio_now") and self.radio_now:
            self.radio_now.setChecked(True)
        if hasattr(self, "date_picker") and self.date_picker:
            self.date_picker.setVisible(False)
        if hasattr(self, "time_picker") and self.time_picker:
            self.time_picker.setVisible(False)
        if hasattr(self, "status_label") and self.status_label:
            self.status_label.setText("准备就绪")
        if hasattr(self, "btn_publish") and self.btn_publish:
            self.btn_publish.setText("添加到发布列表")
        if hasattr(self, "btn_return_to_publish") and self.btn_return_to_publish:
            self.btn_return_to_publish.setVisible(False)
        self._refresh_account_dependent_settings_ui(sync_work_declaration_from_storage=False)
        if not self._is_image_mode and getattr(self, "_auto_match_video_switch", None):
            self._auto_match_video_switch.blockSignals(True)
            self._auto_match_video_switch.setChecked(load_persisted_single_auto_match_video_library())
            self._auto_match_video_switch.setEnabled(True)
            self._auto_match_video_switch.blockSignals(False)
            if self._auto_match_video_switch.isChecked():
                self.btn_add_video.setEnabled(False)
                self._schedule_base_page_timer(
                    "single_auto_video_match",
                    0,
                    self._schedule_single_auto_video_match,
                )
            else:
                self.btn_add_video.setEnabled(True)
        if not self._is_image_mode and getattr(self, "_copywriting_auto_switch", None):
            self._copywriting_auto_switch.blockSignals(True)
            self._copywriting_auto_switch.setChecked(load_persisted_single_auto_match_copywriting())
            self._copywriting_auto_switch.setEnabled(True)
            self._copywriting_auto_switch.blockSignals(False)
            if self._copywriting_auto_switch.isChecked():
                self._schedule_base_page_timer(
                    "single_auto_copywriting_match",
                    0,
                    self._schedule_apply_copywriting_from_library,
                )
        self._update_publish_button_state()

    def _on_publish_success(self, message: str):
        """发布成功：重置为全新页面状态后跳转发布列表"""
        self.status_label.setText("✓ 发布成功！")
        self.btn_publish.setEnabled(True)
        self._reset_form_to_new_page()
        
        if FLUENT_WIDGETS_AVAILABLE:
            from src.ui.utils.safe_info_bar import show_success_toast

            show_success_toast(self, "添加成功", message, duration=3000)
        else:
            from src.ui.utils.fluent_dialogs import show_info
            show_info(self, "成功", message)
        
        self.publish_completed.emit(True, message)
        
        # 保存成功后一律进入「待发布」，并刷新列表使本条可见（与从哪一页进入编辑无关）
        try:
            main_window = self.window()
            self._publish_edit_return_route = None
            # 添加任务后务必让发布列表重新加载，否则新任务（含快手等）不显示
            if hasattr(main_window, "_get_or_create_page"):
                publish_list_page = main_window._get_or_create_page("publish_list_page")
                if publish_list_page and hasattr(publish_list_page, "mark_data_stale"):
                    publish_list_page.mark_data_stale()
            if hasattr(main_window, "navigate_to"):
                main_window.navigate_to("publish_list_page")
            else:
                if hasattr(main_window, "switchTo") and hasattr(main_window, "publish_list_page"):
                    main_window.switchTo(main_window.publish_list_page)
            if hasattr(main_window, "navigationInterface"):
                main_window.navigationInterface.setCurrentItem("publish_list_page")
        except Exception as e:
            logger.error(f"跳转发布列表失败: {e}")
    
    def _on_publish_error(self, error_message: str):
        """发布失败"""
        self.status_label.setText(f"✗ 发布失败: {error_message}")
        self.btn_publish.setEnabled(True)
        
        if FLUENT_WIDGETS_AVAILABLE:
            from src.ui.utils.safe_info_bar import show_error_toast

            show_error_toast(self, "发布失败", error_message, duration=5000)
        else:
            from src.ui.utils.fluent_dialogs import show_warning
            show_warning(self, "错误", f"发布失败: {error_message}")
        
        self.publish_completed.emit(False, error_message)

    def set_publish_data(self, record: dict, *, edit_return_route: Optional[str] = None):
        """回填发布数据 (用于编辑或重新发布)

        Args:
            record: 发布记录字典
            edit_return_route: 从发布管理哪一页进入编辑时的路由键；「返回」时回到该页。
                默认 ``publish_list_page``。保存成功后仍由 ``_on_publish_success`` 统一进入待发布。
        """
        import os
        import asyncio
        # 该页面启用了 _lazy_content；从“发布记录”跳转过来时，可能在页面首次 show 前就调用本方法，
        # 需要先确保 UI 已初始化，否则诸如 btn_publish 等控件尚未创建。
        try:
            if hasattr(self, "_ensure_content"):
                self._ensure_content()
        except Exception:
            # 即使确保内容失败，也尽量继续回填（后续会有 has_attr 保护）
            pass

        # 回填记录中的路径视为手动指定，非本次自动匹配
        self._file_from_auto_library = False
        self._publish_edit_return_route = (edit_return_route or "").strip() or "publish_list_page"

        # 判断是修改列表中的任务，还是仅复用已成功/已归档记录另存为新任务
        # 发布列表含 pending/failed：应对原记录 update，避免「保存修改」却新建一条
        status = (record.get("status") or "").strip().lower()
        if status in ("success", "completed"):
            self.editing_record_id = None
            self._editing_record_original_status = None
            self._editing_record_original_task_source = None
            self._editing_record_original_file_path = None
            if hasattr(self, "btn_publish") and self.btn_publish:
                self.btn_publish.setText("保存为新任务")
        else:
            # pending / failed / running 等均覆盖当前记录（不新建）
            self.editing_record_id = normalize_publish_record_id(record.get("id"))
            self._editing_record_original_status = status
            # 记录原始任务源与素材路径，保存时用于判断是否需要保留账号组标记
            self._editing_record_original_task_source = (record.get("task_source") or "").strip() or None
            self._editing_record_original_file_path = (record.get("file_path") or "").strip()
            if hasattr(self, "btn_publish") and self.btn_publish:
                self.btn_publish.setText("保存修改")

        self._preserve_micro_app_info = ""
        if self.editing_record_id is not None:
            self._preserve_micro_app_info = (record.get("micro_app_info") or "").strip()

        # 1. 基础文本（描述用 setPlainText 以便话题高亮逻辑正确解析）
        title = record.get('title', '')
        description = record.get('description', '')
        if hasattr(self, "title_edit") and self.title_edit:
            self.title_edit.setText(title)
        if hasattr(self, "desc_edit") and self.desc_edit:
            self.desc_edit.setPlainText(normalize_topics_for_paste(description or ""))
        
        # 2. 文件处理（支持图文多路径英文逗号；与发布记录/抖音上传一致）
        file_path = (record.get("file_path") or "").strip()
        paths = _split_comma_paths(file_path) if file_path else []
        existing = [p for p in paths if os.path.exists(p)]
        prefer_image = _record_looks_like_image(record)

        if not file_path:
            self.selected_file_path = ""
            self._update_preview_video_source("")
        elif prefer_image or self._is_image_mode:
            self.selected_file_path = file_path
            if hasattr(self, "file_info_label") and self.file_info_label:
                if existing:
                    self._set_file_info_label_for_paths(existing)
                else:
                    hint = os.path.basename(paths[0]) if paths else file_path
                    extra = f"（共 {len(paths)} 个路径）" if len(paths) > 1 else ""
                    self.file_info_label.setText(f"文件不存在: {hint}{extra}")
            if existing:
                self._create_tracked_task(
                    self._load_thumbnail_async(file_path, prefer_image=True),
                    name="ui.single_publish.load_thumbnail",
                )
            self._update_preview_video_source("")
        else:
            self.selected_file_path = file_path
            if hasattr(self, "file_info_label") and self.file_info_label:
                if existing:
                    p0 = existing[0]
                    size_mb = os.path.getsize(p0) / (1024 * 1024)
                    self.file_info_label.setText(f"{os.path.basename(p0)} | 大小: {size_mb:.2f} MB")
                else:
                    hint = os.path.basename(paths[0]) if paths else file_path
                    self.file_info_label.setText(f"文件不存在: {hint}")
            if existing:
                self._update_preview_video_source(file_path)
            else:
                self._update_preview_video_source("")
        # 3. 封面处理
        cover_path = record.get('cover_path', '')
        if cover_path:
            self._set_cover_type_combo(_COVER_TYPE_LOCAL)
            if hasattr(self, "cover_path_label"):
                import os

                self.selected_cover_path = cover_path
                self.cover_path_label.setText(os.path.basename(cover_path))
        else:
            self._set_cover_type_combo(_COVER_TYPE_FIRST_FRAME)
            if hasattr(self, "cover_path_label"):
                self.selected_cover_path = ""
                self.cover_path_label.setText("未选择本地封面")

        # 4. 标签处理
        tags_str = record.get('tags', '')
        if tags_str:
            # 简单处理：如果描述里没有标签，追加到描述末尾
            # 或者什么都不做，因为当前 UI 没有独立标签输入框
            pass

        more_card = getattr(self, "_more_publish_settings_card", None)
        if more_card is not None:
            more_card.apply_from_publish_record(record, parent=self)

        # 6. 定时发布：有 scheduled_publish_time 则选中「定时」并回填时间。
        # 必须 blockSignals：否则 radio_schedule.setChecked 会触发 _on_schedule_mode_toggled，
        # 进而 _apply_default_schedule_datetime 覆盖库里的时间。
        if (
            hasattr(self, "radio_schedule")
            and hasattr(self, "radio_now")
            and hasattr(self, "date_picker")
            and hasattr(self, "time_picker")
        ):
            st_str = format_schedule_time_st_str(record.get("scheduled_publish_time"))
            if st_str:
                try:
                    from datetime import datetime as _dt

                    dt = _dt.strptime(st_str, "%Y-%m-%d %H:%M")
                    qd = QDate(dt.year, dt.month, dt.day)
                    qt = QTime(dt.hour, dt.minute, 0)
                    self.radio_schedule.blockSignals(True)
                    self.radio_schedule.setChecked(True)
                    self.radio_schedule.blockSignals(False)
                    self.date_picker.setVisible(True)
                    self.time_picker.setVisible(True)
                    self.date_picker.blockSignals(True)
                    self.time_picker.blockSignals(True)
                    try:
                        self.date_picker.setDate(qd)
                        self.time_picker.setTime(qt)
                    finally:
                        self.date_picker.blockSignals(False)
                        self.time_picker.blockSignals(False)
                except ValueError:
                    self.radio_now.setChecked(True)
                    self.date_picker.setVisible(False)
                    self.time_picker.setVisible(False)
            else:
                self.radio_now.setChecked(True)
                self.date_picker.setVisible(False)
                self.time_picker.setVisible(False)

        # 账号回填：仅校验账号是否在账号库中（与 Cookie/登录态无关）；platform_account_id 优先
        self._account_bind_generation = getattr(self, "_account_bind_generation", 0) + 1
        bind_gen = self._account_bind_generation

        target_name = (record.get("platform_username", "") or "").strip()
        target_platform = (record.get("platform", "") or "").strip()
        accounts_now = getattr(self, "available_accounts", None) or []
        found_account = self._find_account_in_available(record, accounts_now) if accounts_now else None

        if found_account:
            self.selected_account = {"type": "account", "data": found_account}
            self._apply_account_label_for_found(record, found_account)
            self._update_publish_button_state()
        else:
            has_hint = bool(target_name) or self._parse_optional_account_id(
                record.get("platform_account_id")
            ) is not None
            if not has_hint:
                self.selected_account = None
                if hasattr(self, "account_label") and self.account_label:
                    self._set_account_label_placeholder()
                self._update_publish_button_state()
            else:
                pid = self._parse_optional_account_id(record.get("platform_account_id"))
                need_defer = (not accounts_now) or (pid is not None)
                if need_defer:
                    platform_cn = self._get_platform_name_cn(target_platform)
                    if target_name:
                        self.account_label.setText(f"{platform_cn} | {target_name}")
                    elif pid is not None:
                        self.account_label.setText(f"{platform_cn} | 账号 ID {pid}")
                    else:
                        self.account_label.setText(f"{platform_cn} | …")
                    self.selected_account = None
                    self._update_publish_button_state()
                    self._create_tracked_task(
                        self._deferred_bind_publish_record_account(record, bind_gen),
                        name="ui.single_publish.bind_record_account",
                    )
                else:
                    self._apply_account_label_missing_in_library(record)
                    self._update_publish_button_state()

        if hasattr(self, "btn_return_to_publish") and self.btn_return_to_publish:
            self.btn_return_to_publish.setVisible(True)

        # 回填发布记录时关闭自动匹配开关（不写偏好）；编辑待发布/失败任务时禁用开关，避免与手动改文件冲突
        if not self._is_image_mode and getattr(self, "_auto_match_video_switch", None):
            self._auto_match_video_switch.blockSignals(True)
            self._auto_match_video_switch.setChecked(False)
            self._auto_match_video_switch.setEnabled(self.editing_record_id is None)
            self._auto_match_video_switch.blockSignals(False)
            if hasattr(self, "btn_add_video") and self.btn_add_video:
                self.btn_add_video.setEnabled(True)
        if not self._is_image_mode and getattr(self, "_copywriting_auto_switch", None):
            self._copywriting_auto_switch.blockSignals(True)
            self._copywriting_auto_switch.setChecked(False)
            self._copywriting_auto_switch.setEnabled(self.editing_record_id is None)
            self._copywriting_auto_switch.blockSignals(False)

        self._update_publish_button_state()
        self._refresh_account_dependent_settings_ui(sync_work_declaration_from_storage=False)
