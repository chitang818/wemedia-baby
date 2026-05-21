"""
设置页面（优化版）
文件路径：src/ui/pages/settings_page.py
功能：设置页面，显示应用设置、账户管理和关于信息，使用 SettingCard 组件优化布局
"""

from typing import Optional
import asyncio
import logging
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QWidget, QLabel, QApplication, QDialog
from PySide6.QtCore import Qt, QUrl, QStandardPaths, QTimer
from qasync import asyncSlot
from PySide6.QtGui import QDesktopServices, QShowEvent

# 导入 PySide6-Fluent-Widgets 组件
from qfluentwidgets import (
    FluentIcon, InfoBar,
    ScrollArea, ExpandLayout, SettingCardGroup,
    SwitchSettingCard, OptionsSettingCard, PushSettingCard, PrimaryPushSettingCard,
    CustomColorSettingCard, HyperlinkCard,
    SettingCard, ComboBox, SwitchButton, InfoBarPosition, PushButton,
    BodyLabel,
)
FLUENT_WIDGETS_AVAILABLE = True

from .base_page import BasePage
from src.ui.components.base_dialog import AppMessageBoxBase
from ..styles import ThemeManager, ThemeMode, get_theme_manager
from ..utils.async_helper import run_async_from_ui
from src.infrastructure.common.path_manager import PathManager
from src.infrastructure.common.di.service_locator import ServiceLocator
from src.infrastructure.common.cache.cache_manager import CacheManager
from src.infrastructure.common.config.config_center import ConfigCenter, get_registered_config_center
from src.infrastructure.common.material_library_manager import MaterialLibraryManager
from src.utils.ffmpeg_installer import FFMPEG_MANUAL_DOWNLOAD_URL
from src.utils.chrome_installer import CHROME_MANUAL_DOWNLOAD_URL, CHROME_DOWNLOAD_PAGE_CN
from src.utils.plugin_settings import (
    get_all_platform_ids,
    get_default_enabled_platform_ids,
    get_enabled_platform_ids,
    set_enabled_platform_ids,
 )

logger = logging.getLogger(__name__)

# 设置页 UI 常量
BROWSER_SCHEME_PLAYWRIGHT = "playwright"
BROWSER_SCHEME_MIXED = "mixed"
FFMPEG_STATUS_COLOR_UNINSTALLED = "#e53935"
# 媒体库未配置时与 FFmpeg 未安装按钮同色（红色提醒）
MEDIA_LIBRARY_UNCONFIGURED_HINT = "尚未配置，请点击右侧按钮选择一个本地文件夹。"
FFMPEG_MSG_TRUNCATE_LEN = 60
FFMPEG_ERROR_TRUNCATE_LEN = 50
CHROME_STATUS_COLOR_UNINSTALLED = "#e53935"
CHROME_MSG_TRUNCATE_LEN = 80
CHROME_ERROR_TRUNCATE_LEN = 80


def _qss_alert_red_push_button() -> str:
    """红色提醒按钮：白字、与 setting_card 中 #primaryButton 相同的圆角与内边距，避免仅改背景时仍为黑字或色相偏差。"""
    c = FFMPEG_STATUS_COLOR_UNINSTALLED
    return (
        "QPushButton {"
        "  color: white;"
        f"  background-color: {c};"
        f"  border: 1px solid {c};"
        "  border-radius: 5px;"
        "  padding: 5px 12px 5px 12px;"
        "  outline: none;"
        "}"
        "QPushButton:hover {"
        "  background-color: #ef5350;"
        "  border: 1px solid #ef5350;"
        "}"
        "QPushButton:pressed {"
        "  color: rgba(255, 255, 255, 0.63);"
        "  background-color: #c62828;"
        "  border: 1px solid #c62828;"
        "}"
    )


def suggest_auto_media_library_base_dir() -> tuple[Path, str, str]:
    """首次配置时推荐的媒体库父目录（其下将创建「媒小宝媒体库」）。

    Windows：若存在可用 D: 盘则用 D:\\；否则用当前用户「文档」目录（QStandardPaths）。
    其他系统：使用用户文档目录。

    Returns:
        (路径, 主按钮文案, 说明区展示的完整路径字符串)
    """
    if sys.platform == "win32":
        d_root = Path("D:/")
        try:
            if d_root.exists() and d_root.is_dir():
                resolved = d_root.resolve()
                return resolved, "自动创建到 D:\\（推荐）", str(resolved)
        except OSError:
            pass
    docs_loc = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )
    doc_path = (
        Path(docs_loc)
        if (docs_loc and str(docs_loc).strip())
        else (Path.home() / "Documents")
    )
    try:
        doc_path = doc_path.expanduser().resolve()
    except Exception:
        doc_path = Path.home() / "Documents"
    return doc_path, "自动创建到我的文档（推荐）", str(doc_path)


class MediaLibraryFirstRunDialog(AppMessageBoxBase):
    """首次未配置媒体库：自动推荐路径或手动选择文件夹。"""

    def __init__(
        self,
        parent: Optional[QWidget],
        *,
        auto_path: Path,
        primary_button_text: str,
        body_text: str,
    ):
        super().__init__(parent, header_title="选择媒体库存储位置")
        self.choice: Optional[str] = None
        self.widget.setMinimumWidth(460)

        self.viewLayout.addSpacing(8)
        body = BodyLabel(body_text, self.widget)
        body.setWordWrap(True)
        self.viewLayout.addWidget(body)

        self.yesButton.setText(primary_button_text)
        self.cancelButton.setText("手动选择文件夹…")
        try:
            if hasattr(self, "buttonGroup") and self.buttonGroup is not None:
                self.buttonGroup.setStyleSheet(
                    "background-color: transparent; border-top: 1px solid #EDEDED;"
                )
        except Exception:
            pass

        lay = getattr(self, "buttonLayout", None)
        if lay is None and hasattr(self, "buttonGroup") and self.buttonGroup is not None:
            lay = self.buttonGroup.layout()
        if lay is not None and lay.indexOf(self.cancelButton) >= 0 and lay.indexOf(self.yesButton) >= 0:
            lay.removeWidget(self.cancelButton)
            lay.removeWidget(self.yesButton)
            lay.addWidget(self.cancelButton)
            lay.addWidget(self.yesButton)

        self.yesButton.clicked.disconnect()
        self.cancelButton.clicked.disconnect()
        self.yesButton.clicked.connect(self._on_auto)
        self.cancelButton.clicked.connect(self._on_manual)

    def _on_auto(self):
        self.choice = "auto"
        self.accept()

    def _on_manual(self):
        self.choice = "manual"
        self.accept()


class SettingsPage(BasePage):
    """设置页面 - 使用 PySide6-Fluent-Widgets 标准组件"""

    _lazy_content = True

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化设置页面"""
        super().__init__("设置", parent)

    def _setup_content(self):
        """延迟构建设置页全部控件（首次 showEvent 时触发）"""
        self.scroll_area = ScrollArea(self)
        self.scroll_widget = QWidget(self.scroll_area)
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setWidgetResizable(True)

        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll_area.viewport().setStyleSheet("background: transparent;")

        self.scroll_widget.setObjectName("scrollWidget")
        self.scroll_widget.setStyleSheet("#scrollWidget { background-color: transparent; }")

        self.expand_layout = ExpandLayout(self.scroll_widget)
        self.expand_layout.setContentsMargins(36, 20, 36, 36)
        self.expand_layout.setSpacing(28)

        self.content_layout.addWidget(self.scroll_area)

        self._create_theme_group()
        self._create_browser_group()
        self._create_plugins_group()
        self._create_data_group()
        self._create_tools_group()
        self._create_system_group()
        self._create_about_group()
        
    def _create_theme_group(self):
        """创建外观设置组"""
        self.theme_group = SettingCardGroup("外观设置", self.scroll_widget)
        
        # 主题模式
        self.theme_card = SettingCard(
            FluentIcon.BRUSH,
            "主题模式",
            "选择应用的主题颜色模式",
            parent=self.theme_group
        )
        
        self.theme_combo = ComboBox(self.theme_card)
        self.theme_combo.addItems(["跟随系统", "浅色模式", "深色模式"])
        self.theme_combo.setMinimumWidth(120)
        
        # 初始化选中状态
        theme_mode = get_theme_manager().get_theme_mode()
        if theme_mode == ThemeMode.AUTO:
            self.theme_combo.setCurrentIndex(0)
        elif theme_mode == ThemeMode.LIGHT:
            self.theme_combo.setCurrentIndex(1)
        elif theme_mode == ThemeMode.DARK:
            self.theme_combo.setCurrentIndex(2)
            
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        
        # 添加控件到卡片布局
        self.theme_card.hBoxLayout.addWidget(self.theme_combo, 0, Qt.AlignRight)
        self.theme_card.hBoxLayout.addSpacing(16)
        
        self.theme_group.addSettingCard(self.theme_card)

        from src.infrastructure.common.config.app_config_keys import KEY_UI, UI_PAGE_ANIMATION_REDUCED

        _pa_initial = False
        _cc = get_registered_config_center()
        if _cc is not None:
            _ui = _cc.get_app_config().get(KEY_UI) or {}
            _pa_initial = bool(_ui.get(UI_PAGE_ANIMATION_REDUCED, False))

        self.page_animation_reduced_card = SwitchSettingCard(
            FluentIcon.FIT_PAGE,
            "减弱页面切换动画",
            "缩短主界面切换时的位移动画并关闭淡入，重型页面首次打开时更利落",
            parent=self.theme_group,
        )
        self.page_animation_reduced_card.setChecked(_pa_initial)
        _pa_switch = getattr(self.page_animation_reduced_card, "switchButton", None)
        if _pa_switch is not None:
            _pa_switch.checkedChanged.connect(self._on_page_animation_reduced_changed)

        self.theme_group.addSettingCard(self.page_animation_reduced_card)
        self.expand_layout.addWidget(self.theme_group)
        
    def _create_browser_group(self):
        """创建浏览器配置组"""
        self.browser_group = SettingCardGroup("浏览器配置", self.scroll_widget)
        
        # 浏览器方案（暂不可修改，后续版本开放）
        self.browser_scheme_card = SettingCard(
            FluentIcon.GLOBE,
            "浏览器方案",
            "选择自动化任务使用的浏览器方案（暂不可修改，后续版本开放）",
            parent=self.browser_group
        )
        
        self.browser_scheme_combo = ComboBox(self.browser_scheme_card)
        self.browser_scheme_combo.addItems(["Playwright (本地 Chrome)"])
        self.browser_scheme_combo.setMinimumWidth(250)
        self.browser_scheme_combo.setEnabled(False)
        self.browser_scheme_combo.setCurrentIndex(0)
        
        self.browser_scheme_card.hBoxLayout.addWidget(self.browser_scheme_combo, 0, Qt.AlignRight)
        self.browser_scheme_card.hBoxLayout.addSpacing(16)
        
        self.browser_group.addSettingCard(self.browser_scheme_card)
        self.expand_layout.addWidget(self.browser_group)

    def _create_plugins_group(self):
        """创建插件配置入口（点击弹窗配置）"""
        self.plugins_group = SettingCardGroup("插件配置", self.scroll_widget)

        # 确保首次有默认值（非阻塞）；必须用已注册单例，勿用无载入了的空 ConfigCenter 覆盖 app_config
        config_center = get_registered_config_center()
        if config_center is not None and not config_center.get_app_config().get("enabled_platform_plugins"):
            async def _init_default():
                try:
                    await set_enabled_platform_ids(config_center, get_default_enabled_platform_ids())
                except Exception as e:
                    logger.debug("初始化默认启用插件失败: %s", e)
            try:
                run_async_from_ui(_init_default)
            except Exception:
                pass

        self.plugins_entry_card = PrimaryPushSettingCard(
            "打开配置",
            FluentIcon.APPLICATION,
            "平台插件启用/禁用",
            "点击弹窗配置启用的平台；禁用平台在账号库入口置灰且不可打开。",
            parent=self.plugins_group
        )
        self.plugins_entry_card.clicked.connect(self._open_plugins_config_dialog)
        self.plugins_group.addSettingCard(self.plugins_entry_card)
        self.expand_layout.addWidget(self.plugins_group)

    def _open_plugins_config_dialog(self):
        config_center = get_registered_config_center()
        if config_center is None:
            logger.warning("ConfigCenter 未注册，无法打开插件配置")
            return

        dialog = _PluginsConfigDialog(config_center, parent=self)
        if dialog.exec():
            try:
                win = self.window()
                acc = getattr(win, "account_page", None)
                if acc and hasattr(acc, "refresh_platform_filter"):
                    acc.refresh_platform_filter()
            except Exception:
                pass
        
    def _create_data_group(self):
        """创建数据管理组"""
        self.data_group = SettingCardGroup("数据管理", self.scroll_widget)
        
        # 数据目录
        data_dir = str(PathManager.get_app_data_dir())
        self.data_dir_card = PushSettingCard(
            "打开目录",
            FluentIcon.FOLDER,
            "数据存储目录",
            data_dir,
            self.data_group
        )
        self.data_dir_card.clicked.connect(self._on_open_data_dir)
        
        # 清理缓存
        self.clear_cache_card = PrimaryPushSettingCard(
            "清理缓存",
            FluentIcon.DELETE,
            "应用缓存管理",
            "清理临时文件、缩略图和会话数据以释放空间",
            self.data_group
        )
        # 调整按钮样式为红色警戒色 (如果 PrimaryPushSettingCard 支持 setCustomBackgroundColor 最好，否则保持默认 Primary 颜色)
        # qfluentwidgets 的 Primary 颜色通常是主题色。为了强调危险，我们可以手动设置样式，但保持一致性也行。
        self.clear_cache_card.clicked.connect(self._on_clear_cache)

        # 媒体库存储（与数据目录同属数据管理）
        display_path = self._material_library_display_path()
        if display_path:
            ml_content = display_path
        else:
            ml_content = MEDIA_LIBRARY_UNCONFIGURED_HINT

        self.material_path_card = PushSettingCard(
            "选择目录",
            FluentIcon.FOLDER,
            "媒体库存储位置",
            ml_content,
            self.data_group,
        )
        self.material_path_card.clicked.connect(self._on_choose_material_library_dir)

        self.material_open_dir_btn = PushButton("打开目录", self.material_path_card)
        self.material_open_dir_btn.clicked.connect(self._on_open_material_library_dir)
        _mlayout = self.material_path_card.hBoxLayout
        _choose_idx = _mlayout.indexOf(self.material_path_card.button)
        if _choose_idx >= 0:
            _mlayout.insertWidget(_choose_idx, self.material_open_dir_btn)
            _mlayout.insertSpacing(_choose_idx + 1, 8)

        self.data_group.addSettingCard(self.material_path_card)
        self.data_group.addSettingCard(self.data_dir_card)
        self.data_group.addSettingCard(self.clear_cache_card)
        self.expand_layout.addWidget(self.data_group)

        self._apply_material_library_reminder_style()

    @staticmethod
    def _material_library_display_path() -> Optional[str]:
        """卡片展示的完整媒体库根路径（含「媒小宝媒体库」目录，尽量为绝对路径）。"""
        try:
            root = MaterialLibraryManager.get_root_dir()
            if root is None:
                return None
            return str(root.expanduser().resolve())
        except Exception as e:
            logger.debug("解析媒体库展示路径失败: %s", e)
            try:
                root = MaterialLibraryManager.get_root_dir()
                return str(root) if root is not None else None
            except Exception:
                return None

    def _apply_material_library_reminder_style(self):
        """未配置媒体库时：「选择目录」按钮红色背景（同 FFmpeg 未安装），说明文字加粗红色。"""
        if not hasattr(self, "material_path_card"):
            return
        display_path = self._material_library_display_path()
        configured = bool(display_path)
        lbl = getattr(self.material_path_card, "contentLabel", None)
        if lbl is not None and callable(lbl):
            lbl = lbl()
        btn = getattr(self.material_path_card, "button", None)
        if btn is not None and callable(btn):
            btn = btn()
        try:
            if configured:
                if btn is not None:
                    btn.setStyleSheet("")
                if lbl is not None:
                    lbl.setTextFormat(Qt.TextFormat.PlainText)
                    lbl.setStyleSheet("")
                    lbl.setText(display_path or "")
                else:
                    self.material_path_card.setContent(display_path or "")
            else:
                if btn is not None:
                    btn.setStyleSheet(_qss_alert_red_push_button())
                if lbl is not None:
                    lbl.setTextFormat(Qt.TextFormat.RichText)
                    lbl.setStyleSheet("")
                    c = FFMPEG_STATUS_COLOR_UNINSTALLED
                    hint = MEDIA_LIBRARY_UNCONFIGURED_HINT
                    lbl.setText(
                        f"<span style='color:{c}; font-weight:700'>{hint}</span>"
                    )
                else:
                    self.material_path_card.setContent(MEDIA_LIBRARY_UNCONFIGURED_HINT)
        except Exception as e:
            logger.debug("应用媒体库提醒样式失败: %s", e)

    def _on_open_material_library_dir(self):
        """在资源管理器中打开当前媒体库根目录（媒小宝媒体库）。"""
        try:
            root = MaterialLibraryManager.ensure_initialized()
            if root is None or not root.is_dir():
                InfoBar.warning(
                    title="无法打开",
                    content="请先在右侧「选择目录」配置有效的媒体库存储位置。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=4000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                return
            url = QUrl.fromLocalFile(str(root.resolve()))
            if not QDesktopServices.openUrl(url):
                InfoBar.warning(
                    title="打开失败",
                    content="系统无法打开该文件夹，请手动在资源管理器中进入。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=4000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
        except Exception as e:
            logger.warning("打开媒体库目录失败: %s", e)
            InfoBar.error(
                title="错误",
                content="打开文件夹时发生异常，请稍后重试。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _commit_material_library_path(self, selected_dir: str) -> None:
        """保存媒体库父目录、初始化目录结构并刷新设置卡片。"""
        selected_dir = (selected_dir or "").strip()
        if not selected_dir:
            return

        async def _save_and_init():
            ok = await MaterialLibraryManager.set_root_base_dir(selected_dir)
            if not ok:
                self.show_error("保存失败", "无法保存媒体库路径，请检查磁盘权限后重试。")
                return

            try:
                root = await MaterialLibraryManager.initialize_and_sync()
            except Exception as e:
                logger.warning("媒体库初始化或同步失败: %s", e, exc_info=True)
                root = None
            if root is None:
                self.show_error(
                    "初始化失败",
                    "无法创建媒体库目录或同步账号文件夹，请检查磁盘权限或选择其他路径。",
                )
                return

            display_path = self._material_library_display_path() or str(
                Path(selected_dir).expanduser().resolve()
            )
            try:
                lbl = getattr(self.material_path_card, "contentLabel", None)
                if lbl is not None:
                    if callable(lbl):
                        lbl = lbl()
                if lbl:
                    lbl.setText(display_path)
                else:
                    self.material_path_card.setContent(display_path)
            except Exception:
                self.material_path_card.setContent(display_path)

            self._apply_material_library_reminder_style()
            self.show_success("已更新", "媒体库存储位置已保存并完成目录初始化。")

        try:
            run_async_from_ui(_save_and_init)
        except Exception as e:
            logger.error("保存媒体库路径并初始化失败: %s", e, exc_info=True)
            self.show_error("错误", "保存媒体库路径失败，请稍后重试。")

    def _on_choose_material_library_dir(self):
        """选择媒体库存储位置：首次可选自动推荐路径或手动选文件夹；已配置则直接打开目录选择。"""
        from PySide6.QtWidgets import QFileDialog

        try:
            root_base = MaterialLibraryManager.get_root_base_dir()
        except Exception:
            root_base = None

        first_time = root_base is None
        if first_time:
            auto_path, primary_lbl, path_display = suggest_auto_media_library_base_dir()
            body = (
                "请选择媒体库的创建方式。\n\n"
                f"若使用自动创建，将在下面路径下生成「媒小宝媒体库」文件夹"
                f"（含视频库、图片库、账号库等）：\n{path_display}\n\n"
                "若需指定其他磁盘或文件夹，请点击「手动选择文件夹」。"
            )
            picker = MediaLibraryFirstRunDialog(
                self,
                auto_path=auto_path,
                primary_button_text=primary_lbl,
                body_text=body,
            )
            if picker.exec() != QDialog.DialogCode.Accepted or not picker.choice:
                return
            if picker.choice == "auto":
                self._commit_material_library_path(str(auto_path))
                return

        dlg = QFileDialog(self, "选择媒体库存储位置")
        dlg.setFileMode(QFileDialog.FileMode.Directory)
        dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dlg.setOption(QFileDialog.Option.DontResolveSymlinks, True)

        if first_time:
            dlg.setDirectoryUrl(QUrl("computer:///"))
        else:
            try:
                dlg.setDirectory(str(Path(root_base).expanduser().resolve()))
            except Exception:
                dlg.setDirectory(str(root_base))

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        files = dlg.selectedFiles()
        selected_dir = (files[0] if files else "").strip()
        if not selected_dir:
            return
        self._commit_material_library_path(selected_dir)

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        if self._content_initialized and hasattr(self, "material_path_card"):
            self._refresh_material_path_card_from_config()

    def _refresh_material_path_card_from_config(self):
        """每次显示设置页时从配置刷新媒体库路径文案（避免与持久化不一致）。"""
        try:
            self._apply_material_library_reminder_style()
        except Exception as e:
            logger.debug("刷新媒体库路径卡片失败: %s", e)

    def _create_tools_group(self):
        """创建工具/依赖组（FFmpeg / Chrome 一键下载）"""
        self.tools_group = SettingCardGroup("工具 / 依赖", self.scroll_widget)
        self.ffmpeg_card = PrimaryPushSettingCard(
            "下载 FFmpeg",
            FluentIcon.DOWNLOAD,
            "FFmpeg",
            "用于视频元数据、缩略图等。正在检测...",
            self.tools_group
        )
        self.ffmpeg_card.clicked.connect(self._on_download_ffmpeg)
        self.tools_group.addSettingCard(self.ffmpeg_card)

        self.chrome_card = PrimaryPushSettingCard(
            "下载 Chrome",
            FluentIcon.DOWNLOAD,
            "Google Chrome",
            "用于浏览器自动化。若浏览器功能无法启动，请先在此安装 Chrome。正在检测...",
            self.tools_group
        )
        self.chrome_card.clicked.connect(self._on_download_chrome)
        self.tools_group.addSettingCard(self.chrome_card)

        self.expand_layout.addWidget(self.tools_group)
        self._check_ffmpeg_async()
        self._check_chrome_async()

    def _check_ffmpeg_async(self):
        """异步检测 FFmpeg 安装状态，避免阻塞 UI 线程"""
        from ..utils.async_helper import AsyncWorker
        
        def check_sync():
            from src.utils.ffmpeg_installer import check_ffmpeg_installed
            is_installed, _ = check_ffmpeg_installed()
            return is_installed

        worker = AsyncWorker(check_sync)
        worker.setParent(self)
        worker.finished.connect(self._on_ffmpeg_check_done)
        worker.error.connect(lambda e: self._update_ffmpeg_card_status(
            "用于视频元数据、缩略图等。当前状态：未知。"
        ))
        worker.start()

    def _on_ffmpeg_check_done(self, is_installed):
        """FFmpeg 检测完成回调"""
        if is_installed:
            text = "用于视频元数据、缩略图等。当前状态：已安装。"
            try:
                from src.utils import video_metadata

                video_metadata.invalidate_ffmpeg_availability_cache()
                video_metadata._initialize_ffmpeg_path(force_refresh=True)
            except Exception as e:
                logger.debug("设置页同步 video_metadata FFmpeg 路径失败: %s", e)
        else:
            text = "用于视频元数据、缩略图等。当前状态：未安装，可点击按钮一键下载。"
        self._update_ffmpeg_card_status(text)

    def _update_ffmpeg_card_status(self, content: str):
        """更新 FFmpeg 卡片上的状态文字，仅将「未安装」三字显示为红色；未安装时按钮背景也为红色"""
        if not hasattr(self, "ffmpeg_card") or not self.ffmpeg_card:
            return
        is_uninstalled = "未安装" in (content or "")
        try:
            # contentLabel 在 qfluentwidgets 中可能是属性（直接是 QLabel）或方法，需兼容
            lbl = getattr(self.ffmpeg_card, "contentLabel", None)
            if lbl is not None:
                if callable(lbl):
                    lbl = lbl()
                if lbl:
                    if is_uninstalled:
                        lbl.setTextFormat(Qt.TextFormat.RichText)
                        html = (content or "").replace("未安装", f"<span style='color:{FFMPEG_STATUS_COLOR_UNINSTALLED}'>未安装</span>")
                        lbl.setText(html)
                    else:
                        lbl.setTextFormat(Qt.TextFormat.PlainText)
                        lbl.setText(content or "")
        except Exception as e:
            logger.debug("通过 contentLabel 更新 FFmpeg 状态失败，回退 setContent: %s", e)
            self.ffmpeg_card.setContent(content)
        # 未安装时「下载 FFmpeg」按钮背景设为红色，已安装时恢复主题色
        try:
            btn = getattr(self.ffmpeg_card, "button", None)
            if btn is not None and callable(btn):
                btn = btn()
            if btn:
                if is_uninstalled:
                    btn.setStyleSheet(_qss_alert_red_push_button())
                else:
                    btn.setStyleSheet("")
        except Exception as e:
            logger.debug("设置 FFmpeg 按钮样式失败: %s", e)

    # ---------------- Chrome ----------------
    def _check_chrome_async(self):
        """异步检测 Chrome 安装状态，避免阻塞 UI 线程"""
        from ..utils.async_helper import AsyncWorker

        def check_sync():
            from src.utils.chrome_installer import detect_chrome
            return detect_chrome()

        worker = AsyncWorker(check_sync)
        worker.setParent(self)
        worker.finished.connect(self._on_chrome_check_done)
        worker.error.connect(lambda _: self._update_chrome_card_status(
            "用于浏览器自动化。当前状态：未知。"
        ))
        worker.start()

    def _on_chrome_check_done(self, result):
        """Chrome 检测完成回调"""
        installed, info = result
        if installed:
            ver = (info or {}).get("version") or "未知版本"
            path = (info or {}).get("path") or "未知路径"
            text = f"用于浏览器自动化。当前状态：已安装（{ver}）。路径：{path}"
        else:
            text = "用于浏览器自动化。若浏览器功能无法启动，请先在此安装 Chrome。当前状态：未安装，可点击按钮打开下载页手动安装。"
        self._update_chrome_card_status(text)

    def _update_chrome_card_status(self, content: str):
        """更新 Chrome 卡片状态文字；未安装时按钮背景为红色"""
        if not hasattr(self, "chrome_card") or not self.chrome_card:
            return
        is_uninstalled = "未安装" in (content or "")
        try:
            lbl = getattr(self.chrome_card, "contentLabel", None)
            if lbl is not None:
                if callable(lbl):
                    lbl = lbl()
                if lbl:
                    if is_uninstalled:
                        lbl.setTextFormat(Qt.TextFormat.RichText)
                        html = (content or "").replace(
                            "未安装",
                            f"<span style='color:{CHROME_STATUS_COLOR_UNINSTALLED}'>未安装</span>"
                        )
                        lbl.setText(html)
                    else:
                        lbl.setTextFormat(Qt.TextFormat.PlainText)
                        lbl.setText(content or "")
        except Exception as e:
            logger.debug("通过 contentLabel 更新 Chrome 状态失败，回退 setContent: %s", e)
            self.chrome_card.setContent(content)

        try:
            btn = getattr(self.chrome_card, "button", None)
            if btn is not None and callable(btn):
                btn = btn()
            if btn:
                if is_uninstalled:
                    btn.setStyleSheet(_qss_alert_red_push_button())
                else:
                    btn.setStyleSheet("")
        except Exception as e:
            logger.debug("设置 Chrome 按钮样式失败: %s", e)

    def _on_download_chrome(self):
        """设置页：检测 Chrome 状态；已安装则弹窗提示，未安装则用默认浏览器打开下载页由用户手动安装"""
        self._update_chrome_card_status("正在检测 Chrome…")
        self.chrome_card.setEnabled(False)

        from ..utils.async_helper import AsyncWorker

        def pre_check():
            from src.utils.chrome_installer import detect_chrome
            return detect_chrome()

        worker = AsyncWorker(pre_check)
        worker.setParent(self)
        worker.finished.connect(self._on_chrome_pre_check_done)
        worker.error.connect(lambda _: self._open_chrome_download_page())
        worker.start()

    def _on_chrome_pre_check_done(self, result):
        """Chrome 检测完成：已安装则弹窗通知，未安装则打开下载页"""
        self.chrome_card.setEnabled(True)
        if not result or not isinstance(result, (tuple, list)) or len(result) < 1:
            self._open_chrome_download_page()
            return
        installed, _ = result
        if installed:
            self.show_success("Chrome 已安装", "检测到 Google Chrome 已安装。")
            self._check_chrome_async()
            return
        self._open_chrome_download_page()

    def _open_chrome_download_page(self):
        """用本地默认浏览器打开 Chrome 下载页，由用户手动下载安装"""
        self.chrome_card.setEnabled(True)
        url = QUrl(CHROME_DOWNLOAD_PAGE_CN)
        if QDesktopServices.openUrl(url):
            self._update_chrome_card_status(
                "已打开下载页，请手动下载安装。安装完成后可点击本按钮再次检测。"
            )
        else:
            self._update_chrome_card_status(
                f"无法打开浏览器，请手动访问：{CHROME_DOWNLOAD_PAGE_CN}"
            )
        
    def _create_system_group(self):
        """创建系统选项组"""
        self.system_group = SettingCardGroup("系统选项", self.scroll_widget)
        
        # 开机自启动
        self.auto_start_card = SettingCard(
            FluentIcon.POWER_BUTTON,
            "开机自启动",
            "启用后，系统启动时自动运行本软件",
            parent=self.system_group
        )
        self.auto_start_switch = SwitchButton(self.auto_start_card)
        self.auto_start_switch.setOnText("开")
        self.auto_start_switch.setOffText("关")
        self.auto_start_card.hBoxLayout.addWidget(self.auto_start_switch, 0, Qt.AlignRight)
        self.auto_start_card.hBoxLayout.addSpacing(16)
        
        # 窗口关闭行为（新版三选一：每次询问/最小化到托盘/退出应用）
        self.close_behavior_card = SettingCard(
            FluentIcon.QUESTION,
            "窗口关闭行为",
            "选择点击关闭按钮后的行为：每次询问/最小化到托盘/退出应用",
            parent=self.system_group,
        )
        self.close_behavior_combo = ComboBox(self.close_behavior_card)
        self.close_behavior_combo.addItems(["每次询问", "最小化到托盘", "退出应用"])
        self.close_behavior_combo.setMinimumWidth(220)
        self.close_behavior_card.hBoxLayout.addWidget(
            self.close_behavior_combo, 0, Qt.AlignRight
        )
        self.close_behavior_card.hBoxLayout.addSpacing(16)

        # 显示指纹环境标签页
        self.env_tab_card = SettingCard(
            FluentIcon.GLOBE,
            "显示指纹环境标签页",
            "打开账号浏览器时，在第一个标签页显示账号指纹环境信息（关闭后只保留业务标签页，方便排查问题）",
            parent=self.system_group
        )
        self.env_tab_switch = SwitchButton(self.env_tab_card)
        self.env_tab_switch.setOnText("开")
        self.env_tab_switch.setOffText("关")
        self.env_tab_card.hBoxLayout.addWidget(self.env_tab_switch, 0, Qt.AlignRight)
        self.env_tab_card.hBoxLayout.addSpacing(16)
        
        self.system_group.addSettingCard(self.auto_start_card)
        self.system_group.addSettingCard(self.close_behavior_card)
        self.system_group.addSettingCard(self.env_tab_card)
        self.expand_layout.addWidget(self.system_group)

        self._load_system_settings()
        self.auto_start_switch.checkedChanged.connect(self._on_auto_start_changed)
        self.close_behavior_combo.currentIndexChanged.connect(
            self._on_close_behavior_changed
        )
        self.env_tab_switch.checkedChanged.connect(self._on_env_tab_changed)

    # ---- 系统选项：配置读写与功能实现 ----

    def _load_system_settings(self):
        """从配置中心读取系统选项的开关状态"""
        try:
            config_center = ServiceLocator().get(ConfigCenter)
            app_cfg = config_center.get_app_config()
            # 新版三选一：main_window_close_behavior
            from src.infrastructure.common.config.app_config_keys import (
                MAIN_WINDOW_CLOSE_BEHAVIOR,
            )

            behavior = str(app_cfg.get(MAIN_WINDOW_CLOSE_BEHAVIOR, "ask") or "ask")
            idx_map = {"ask": 0, "tray": 1, "exit": 2}
            self.close_behavior_combo.setCurrentIndex(idx_map.get(behavior, 0))

            if app_cfg.get("auto_start", False):
                self.auto_start_switch.setChecked(True)
            # 指纹环境标签页：默认开启，读取持久化值
            show_env = app_cfg.get("show_environment_info_tab", False)
            self.env_tab_switch.setChecked(bool(show_env))
        except Exception as e:
            logger.warning("加载系统选项配置失败: %s", e)

    def _on_tray_changed(self, checked: bool):
        """关闭时最小化到托盘 开关变更"""
        logger.info("托盘开关变更: checked=%s", checked)
        async def _save():
            config_center = ServiceLocator().get(ConfigCenter)
            await config_center.initialize()
            app_cfg = {**config_center.get_app_config()}
            app_cfg["minimize_to_tray"] = checked
            logger.info("正在保存托盘配置: minimize_to_tray=%s", checked)
            await config_center.update("app_config", app_cfg)
            logger.info("托盘配置保存成功: minimize_to_tray=%s", checked)
        try:
            run_async_from_ui(_save)
        except Exception as e:
            logger.error("保存托盘配置失败: %s", e)

        # 同步通知主窗口切换托盘图标可见性
        main_win = self._find_main_window()
        if main_win and hasattr(main_win, 'set_tray_visible'):
            main_win.set_tray_visible(checked)

    def _on_close_remind_changed(self, checked: bool):
        """关闭软件弹窗是否提醒 开关变更"""
        async def _save():
            config_center = ServiceLocator().get(ConfigCenter)
            await config_center.initialize()
            app_cfg = {**config_center.get_app_config()}
            app_cfg["main_window_close_remind"] = bool(checked)
            await config_center.update("app_config", app_cfg)

        try:
            run_async_from_ui(_save)
        except Exception as e:
            logger.error("保存关闭弹窗提醒配置失败: %s", e)

    def _on_close_behavior_changed(self, index: int):
        """窗口关闭行为（三选一）变更"""
        behavior_map = {0: "ask", 1: "tray", 2: "exit"}
        behavior = behavior_map.get(index, "ask")

        async def _save():
            config_center = ServiceLocator().get(ConfigCenter)
            await config_center.initialize()
            app_cfg = {**config_center.get_app_config()}
            from src.infrastructure.common.config.app_config_keys import (
                MAIN_WINDOW_CLOSE_BEHAVIOR,
            )

            app_cfg[MAIN_WINDOW_CLOSE_BEHAVIOR] = str(behavior)
            await config_center.update("app_config", app_cfg)

        try:
            run_async_from_ui(_save)
        except Exception as e:
            logger.error("保存窗口关闭行为配置失败: %s", e)
            return

        # 同步托盘图标显示状态（仅尽量做到实时可见性，不强行影响隐藏主窗口逻辑）
        try:
            main_win = self._find_main_window()
            if main_win and hasattr(main_win, "set_tray_visible"):
                main_win.set_tray_visible(behavior == "tray")
        except Exception:
            pass

    def _on_env_tab_changed(self, checked: bool):
        """显示指纹环境标签页 开关变更"""
        async def _save():
            config_center = ServiceLocator().get(ConfigCenter)
            await config_center.initialize()
            app_cfg = {**config_center.get_app_config()}
            app_cfg["show_environment_info_tab"] = checked
            await config_center.update("app_config", app_cfg)
        try:
            run_async_from_ui(_save)
        except Exception as e:
            logger.error("保存指纹环境标签页配置失败: %s", e)

    def _on_auto_start_changed(self, checked: bool):
        """开机自启动 开关变更"""
        ok = self._set_windows_auto_start(checked)
        if not ok:
            # 注册表操作失败，回退开关状态
            self.auto_start_switch.blockSignals(True)
            self.auto_start_switch.setChecked(not checked)
            self.auto_start_switch.blockSignals(False)
            InfoBar.error(
                title="操作失败",
                content="无法修改开机自启动设置，可能需要以管理员权限运行。",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )
            return

        async def _save():
            config_center = ServiceLocator().get(ConfigCenter)
            await config_center.initialize()
            app_cfg = {**config_center.get_app_config()}
            app_cfg["auto_start"] = checked
            await config_center.update("app_config", app_cfg)
        try:
            run_async_from_ui(_save)
        except Exception as e:
            logger.error("保存开机自启动配置失败: %s", e)

    @staticmethod
    def _set_windows_auto_start(enable: bool) -> bool:
        """通过 Windows 注册表设置/取消开机自启动

        注册表位置：HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
        值名称：媒小宝
        值数据：可执行文件路径（打包后为 exe，开发环境为 pythonw + main.py）
        """
        if sys.platform != "win32":
            return True
        import winreg
        REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
        VALUE_NAME = "媒小宝"
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE
            )
            if enable:
                exe_path = SettingsPage._get_app_executable_path()
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            logger.info("开机自启动 %s 成功", "开启" if enable else "关闭")
            return True
        except Exception as e:
            logger.error("设置开机自启动失败: %s", e)
            return False

    @staticmethod
    def _get_app_executable_path() -> str:
        """获取当前应用的可执行路径，兼容打包和开发环境"""
        if getattr(sys, 'frozen', False):
            return f'"{sys.executable}"'
        return f'"{sys.executable}" "{os.path.abspath("main.py")}"'

    def _find_main_window(self):
        """查找 MainWindow 实例"""
        for widget in QApplication.topLevelWidgets():
            if widget.__class__.__name__ == "MainWindow":
                return widget
        return None
        
    def _create_about_group(self):
        """创建关于组"""
        from config.feature_flags import FeatureFlags

        self.about_group = SettingCardGroup("关于", self.scroll_widget)

        is_52pojie = FeatureFlags.is_52pojie()

        try:
            from src.version import __version__
            version_str = __version__
        except Exception as e:
            logger.debug("读取版本号失败: %s", e)
            version_str = "未知"

        app_label = "媒小宝-吾爱破解论坛特别版" if is_52pojie else "媒小宝"

        if not is_52pojie:
            self.check_update_card = PushSettingCard(
                "检查更新",
                FluentIcon.INFO,
                app_label,
                f"版本 {version_str} © 2026 媒小宝团队",
                self.about_group
            )
            self.check_update_card.clicked.connect(self._on_check_update)
        else:
            self.version_card = SettingCard(
                FluentIcon.INFO,
                app_label,
                f"版本 {version_str}",
                self.about_group
            )

        if is_52pojie:
            self.tutorial_card = PushSettingCard(
                "访问论坛",
                FluentIcon.BOOK_SHELF,
                "使用帮助",
                "访问吾爱破解论坛获取使用帮助",
                self.about_group
            )
        else:
            self.tutorial_card = PushSettingCard(
                "软件使用教程",
                FluentIcon.BOOK_SHELF,
                "使用帮助",
                "查看飞书文档中的软件使用教程",
                self.about_group
            )
        self.tutorial_card.clicked.connect(self._on_open_tutorial)

        if not is_52pojie:
            self.feedback_card = PushSettingCard(
                "反馈问题",
                FluentIcon.FEEDBACK,
                "帮助与反馈",
                "访问 GitHub 提交 Issue 或获取帮助",
                self.about_group
            )
            self.feedback_card.clicked.connect(self._on_feedback)

        if is_52pojie:
            self.about_group.addSettingCard(self.version_card)
        else:
            self.about_group.addSettingCard(self.check_update_card)
        self.about_group.addSettingCard(self.tutorial_card)
        if not is_52pojie:
            self.about_group.addSettingCard(self.feedback_card)
        self.expand_layout.addWidget(self.about_group)

    # --- Callbacks ---
    
    def _on_page_animation_reduced_changed(self, checked: bool):
        """持久化「减弱页面切换动画」；与 page_animation_prefs 读取路径一致，立即生效。"""
        from src.infrastructure.common.config.app_config_keys import KEY_UI, UI_PAGE_ANIMATION_REDUCED
        from src.infrastructure.common.config.app_config_merge import merge_app_config

        async def _save() -> None:
            cc = get_registered_config_center()
            if cc is None:
                return
            ui = dict(cc.get_app_config().get(KEY_UI) or {})
            ui[UI_PAGE_ANIMATION_REDUCED] = bool(checked)
            await merge_app_config(cc, {KEY_UI: ui})

        try:
            run_async_from_ui(_save)
            self.show_success("设置已保存", "页面切换动画已按您的选择更新，无需重启")
        except Exception as e:
            logger.error("保存页面动画偏好失败: %s", e, exc_info=True)
            self.show_error("错误", "保存设置失败，请重试")

    def _on_theme_changed(self, index: int):
        """主题切换"""
        text = self.theme_combo.currentText()
        
        try:
            theme_mgr = get_theme_manager()
            if text == "跟随系统":
                theme_mgr.set_theme_mode(ThemeMode.AUTO)
            elif text == "浅色模式":
                theme_mgr.set_theme_mode(ThemeMode.LIGHT)
            elif text == "深色模式":
                theme_mgr.set_theme_mode(ThemeMode.DARK)
            
            self.show_success("主题已更改", "新的主题设置已生效")
            if hasattr(self, "material_path_card"):
                self._apply_material_library_reminder_style()
        except Exception as e:
            logger.error(f"切换主题失败: {e}")

    def _on_browser_scheme_changed(self, index: int):
        """浏览器方案切换"""
        settings_text = self.browser_scheme_combo.currentText()
        try:
            scheme = BROWSER_SCHEME_PLAYWRIGHT if "Undetected" in settings_text else BROWSER_SCHEME_MIXED
            
            config_center = ServiceLocator().get(ConfigCenter)
            
            import asyncio
            async def update_config():
                try:
                    await config_center.initialize()
                    app_config = {**config_center.get_app_config()}
                    app_config["browser_scheme"] = scheme
                    await config_center.update("app_config", app_config)
                    logger.info(f"浏览器方案已更新为: {scheme}")
                except Exception as e:
                    logger.error(f"保存配置失败: {e}")

            try:
                run_async_from_ui(update_config)
            except Exception as e:
                logger.error(f"调度配置更新任务失败: {e}")
                
            self.show_success("设置已保存", "浏览器方案已更新，重启软件后生效")
            
        except Exception as e:
            logger.error(f"切换浏览器方案失败: {e}")
            self.show_error("错误", "保存设置失败")

    def _on_download_ffmpeg(self):
        """设置页：静默下载 FFmpeg 到用户数据目录，状态与进度显示在卡片上。若已安装则提示无需下载。"""
        self._update_ffmpeg_card_status("正在检测 FFmpeg…")
        self.ffmpeg_card.setEnabled(False)

        from ..utils.async_helper import AsyncWorker

        def pre_check():
            from src.utils.ffmpeg_installer import check_ffmpeg_installed
            return check_ffmpeg_installed()

        worker = AsyncWorker(pre_check)
        worker.setParent(self)
        worker.finished.connect(self._on_ffmpeg_pre_check_done)
        worker.error.connect(lambda _: self._start_ffmpeg_download())
        worker.start()

    def _on_ffmpeg_pre_check_done(self, result):
        """FFmpeg 安装前检测完成"""
        is_installed, _ = result
        if is_installed:
            self.ffmpeg_card.setEnabled(True)
            self.show_success("FFmpeg 已安装", "检测到 FFmpeg 已安装，无需重复下载。")
            self._update_ffmpeg_card_status("用于视频元数据、缩略图等。当前状态：已安装。")
            return
        self._start_ffmpeg_download()

    def _start_ffmpeg_download(self):
        """启动 FFmpeg 下载"""
        self._update_ffmpeg_card_status("正在下载 FFmpeg… 0%")
        self.ffmpeg_card.setEnabled(False)

        def progress_cb(current: int, total: int):
            if total and total > 0:
                pct = min(100, int(100 * current / total))
                self._update_ffmpeg_card_status(f"正在下载 FFmpeg… {pct}%")
            else:
                self._update_ffmpeg_card_status("正在下载 FFmpeg…")

        async def download_ffmpeg_task():
            try:
                from src.utils.ffmpeg_installer import download_and_install_ffmpeg_async
                ok, msg = await download_and_install_ffmpeg_async(progress_callback=progress_cb)
                self.ffmpeg_card.setEnabled(True)
                if ok:
                    from src.utils import video_metadata
                    video_metadata._initialize_ffmpeg_path(force_refresh=True)
                    self._update_ffmpeg_card_status("已安装，可立即使用。")
                    self.show_success("FFmpeg 已安装", msg)
                else:
                    self._update_ffmpeg_card_status(
                        f"下载失败：{msg[:FFMPEG_MSG_TRUNCATE_LEN]}{'…' if len(msg) > FFMPEG_MSG_TRUNCATE_LEN else ''}。可点击按钮重试或从 {FFMPEG_MANUAL_DOWNLOAD_URL} 手动下载。"
                    )
                    self.show_error("下载失败", msg + "\n\n可手动从 https://www.gyan.dev/ffmpeg/builds/ 下载。")
            except Exception as e:
                self.ffmpeg_card.setEnabled(True)
                logger.exception("下载 FFmpeg 异常")
                self._update_ffmpeg_card_status(f"下载异常：{str(e)[:FFMPEG_ERROR_TRUNCATE_LEN]}…。可点击按钮重试。")
                self.show_error("下载失败", str(e))

        try:
            run_async_from_ui(download_ffmpeg_task)
        except Exception as e:
            self.ffmpeg_card.setEnabled(True)
            logger.error(f"启动下载任务失败: {e}")
            self._update_ffmpeg_card_status("用于视频元数据、缩略图等。下载任务启动失败，请重试。")
            self.show_error("启动失败", "无法启动下载任务，请稍后重试")

    def _on_open_data_dir(self):
        """打开数据目录"""
        try:
            data_dir = PathManager.get_app_data_dir()
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir)))
        except Exception as e:
            self.show_error("错误", f"无法打开目录: {e}")

    def _on_clear_cache(self):
        """清理缓存"""
        from src.ui.utils.fluent_dialogs import show_confirm
        if show_confirm(self.window(), "确认清理", "确定要清理所有应用缓存吗？\n这将删除临时文件、历史日志和浏览器环境以释放空间。\n(已登录账号的凭证不会被删除)"):
            # 1. 显示“清理中”提示
            info_bar = InfoBar.info(
                title="正在清理",
                content="由于涉及日志和临时文件，清理可能需要几秒钟，请稍候...",
                orient=Qt.Horizontal,
                isClosable=False,
                duration=-1, # 永不关闭直到手动移除
                position=InfoBarPosition.TOP,
                parent=self
            )
            
            async def clear_task():
                try:
                    cache_mgr = ServiceLocator().get(CacheManager)
                    # 执行深度清理并获取结果
                    results = await cache_mgr.clear()
                    
                    # 2. 移除加载中提示
                    info_bar.close()
                    
                    # 3. 构造结果摘要
                    summary = []
                    if results.get("l2_cleared", 0) > 0:
                        summary.append(f"数据缓存: {results['l2_cleared']} 个文件")
                    if results.get("logs_cleared", 0) > 0:
                        summary.append(f"运行日志: {results['logs_cleared']} 个文件")
                    if results.get("browser_temp_cleared", 0) > 0:
                        summary.append(f"临时环境: {results['browser_temp_cleared']} 个目录")
                    
                    content = "应用缓存已深度清理。"
                    if summary:
                        content += "\n详细: " + ", ".join(summary)
                    
                    self.show_success("清理成功", content)
                except Exception as e:
                    if info_bar: info_bar.close()
                    self.show_error("错误", f"清理缓存过程中发生异常: {e}")
            
            try:
                run_async_from_ui(clear_task)
            except Exception as e:
                if info_bar: info_bar.close()
                logger.error(f"启动清理任务失败: {e}")
                self.show_error("启动失败", "无法启动异步清理任务")

    def _check_update_info_parent(self) -> QWidget:
        """InfoBar/弹窗父级：用主窗口，避免嵌套 ScrollArea 内提示不可见"""
        return self.window() or self

    @staticmethod
    def _resolve_push_setting_button(card) -> Optional[QWidget]:
        """兼容 PushSettingCard.button 为 QPushButton 属性或无参方法两种形态。"""
        if card is None:
            return None
        btn = getattr(card, "button", None)
        if btn is None:
            return None
        if isinstance(btn, QWidget):
            return btn
        if callable(btn):
            resolved = btn()
            return resolved if isinstance(resolved, QWidget) else None
        return None

    @asyncSlot()
    async def _on_check_update(self):
        """手动检查更新：请求 Gitee version.json，下载链接以库中 download_url 为准"""
        parent = self._check_update_info_parent()
        btn = self._resolve_push_setting_button(getattr(self, "check_update_card", None))
        info_bar = None
        if btn is not None:
            btn.setEnabled(False)
        try:
            info_bar = InfoBar.info(
                title="检查更新",
                content="正在连接更新服务器，请稍候…",
                orient=Qt.Orientation.Horizontal,
                isClosable=False,
                duration=-1,
                position=InfoBarPosition.TOP,
                parent=parent,
            )
            from src.services.update_check_service import check_for_updates

            result = await check_for_updates(force_refresh=True)
        except Exception:
            logger.exception("检查更新失败")
            from src.services.update_check_service import UpdateCheckResult

            try:
                from src.version import __version__ as ver
            except Exception:
                ver = "0.0.0"
            err_result = UpdateCheckResult(
                has_update=False,
                current_version=ver,
                error="检查更新失败，请稍后重试",
            )
            self._schedule_base_page_timer(
                "settings_apply_update_result",
                0,
                lambda r=err_result: self._apply_update_result(r),
            )
            return
        finally:
            if info_bar is not None:
                try:
                    info_bar.close()
                except Exception:
                    pass
            if btn is not None:
                btn.setEnabled(True)
        # 弹窗须在主线程同步展示，不可在协程内直接 exec（会与 qasync 冲突导致无响应）
        self._schedule_base_page_timer(
            "settings_apply_update_result",
            0,
            lambda r=result: self._apply_update_result(r),
        )

    def _apply_update_result(self, result):
        """根据更新检查结果弹窗或提示；有新版本则强制更新（弹窗关闭后退出）"""
        from src.ui.utils.fluent_dialogs import show_error, show_info, show_force_update_confirm

        parent = self._check_update_info_parent()
        if result.error:
            show_error(parent, "检查更新", result.error)
            return
        if result.has_update and result.remote_version and result.download_url:
            if show_force_update_confirm(
                parent,
                result.current_version,
                result.remote_version or "",
                result.notes or "",
            ):
                QDesktopServices.openUrl(QUrl(result.download_url))
            QApplication.quit()
        else:
            remote = result.remote_version or ""
            msg = f"当前版本 {result.current_version} 已是最新。"
            if remote:
                msg += f"\n云端版本：{remote}"
            show_info(parent, "检查更新", msg)

    def _on_open_tutorial(self):
        """打开使用帮助：52POJIE 跳转论坛，其他跳转飞书文档"""
        from config.feature_flags import FeatureFlags
        if FeatureFlags.is_52pojie():
            url = QUrl("https://www.52pojie.cn/forum.php")
        else:
            url = QUrl("https://my.feishu.cn/docx/DpotdqxU8owf15xD54oc6P9KnWf?from=from_copylink")
        if not QDesktopServices.openUrl(url):
            self.show_error("无法打开链接", "请手动在浏览器中访问该链接")

    def _on_feedback(self):
        """打开帮助与反馈（GitHub Issues），使用系统默认浏览器"""
        url = QUrl("https://github.com/chitang818/wemedia-baby/issues")
        if not QDesktopServices.openUrl(url):
            self.show_error("无法打开链接", "请手动在浏览器中访问：https://github.com/chitang818/wemedia-baby/issues")


class _PluginsConfigDialog(AppMessageBoxBase):
    """弹窗：配置平台插件启用/禁用"""

    def __init__(self, config_center: ConfigCenter, parent: Optional[QWidget] = None):
        super().__init__(parent, header_title="插件配置")
        self._config_center = config_center

        from qfluentwidgets import BodyLabel

        self.viewLayout.addWidget(BodyLabel("选择启用的平台插件（禁用的平台在账号库入口置灰且不可打开）。", self.widget))

        self.widget.setMinimumWidth(640)

        self._cards: dict[str, SwitchSettingCard] = {}

        content = ScrollArea(self.widget)
        content.setWidgetResizable(True)
        content.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        content.viewport().setStyleSheet("background: transparent;")
        inner = QWidget(content)
        content.setWidget(inner)

        inner_layout = ExpandLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(8)

        group = SettingCardGroup("平台列表", inner)

        enabled_ids = set(get_enabled_platform_ids(self._config_center))
        all_ids = get_all_platform_ids()
        # 平台排序：按“选择平台”页面的展示顺序（见 add_account_dialog.PLATFORM_CONFIG）
        try:
            from src.ui.account.add_account_dialog import PLATFORM_CONFIG as _PLATFORM_CONFIG
            preferred_order = list(_PLATFORM_CONFIG.keys())
            order_index = {pid: i for i, pid in enumerate(preferred_order)}
            all_ids = sorted(all_ids, key=lambda pid: (order_index.get(pid, 10**9), pid))
        except Exception:
            pass
        from src.utils.platform_names import get_platform_display_name
        for pid in all_ids:
            card = SwitchSettingCard(
                FluentIcon.APPLICATION,
                get_platform_display_name(pid),
                "启用后可添加/登录该平台账号；禁用后入口置灰不可打开。",
                parent=group
            )
            card.setChecked(pid in enabled_ids)
            group.addSettingCard(card)
            self._cards[pid] = card

        inner_layout.addWidget(group)
        self.viewLayout.addWidget(content)

        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")
        self._reorder_buttons()
        try:
            self.yesButton.clicked.disconnect()
        except Exception:
            pass
        self.yesButton.clicked.connect(self._on_save_clicked)

    def _reorder_buttons(self):
        button_layout = getattr(self, "buttonLayout", None)
        if button_layout is None:
            button_layout = self.buttonGroup.layout()
        if button_layout:
            button_layout.removeWidget(self.yesButton)
            button_layout.removeWidget(self.cancelButton)
            button_layout.addWidget(self.cancelButton)
            button_layout.addWidget(self.yesButton)

    def keyPressEvent(self, event):
        from PySide6.QtCore import Qt
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _on_save_clicked(self):
        enabled = [pid for pid, card in self._cards.items() if card.isChecked()]

        async def _save():
            await set_enabled_platform_ids(self._config_center, enabled)

        try:
            run_async_from_ui(_save)
            InfoBar.success(
                title="已保存",
                content="插件启用配置已保存。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=2000,
                position=InfoBarPosition.TOP,
                parent=self
            )
            self.accept()
        except Exception as e:
            InfoBar.error(
                title="保存失败",
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self
            )
