"""
基础页面类
文件路径：src/ui/pages/base_page.py
功能：提供所有页面的基类，统一页面布局和样式
"""

import time
from typing import Callable, Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QAbstractItemView, QGraphicsOpacityEffect
from PySide6.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QShowEvent
import logging

# 导入 PySide6-Fluent-Widgets 组件
from qfluentwidgets import ScrollArea, InfoBar, InfoBarPosition
FLUENT_WIDGETS_AVAILABLE = True

logger = logging.getLogger(__name__)

_FADE_EASING = QEasingCurve.OutCubic


class BasePage(QWidget):
    """基础页面类
    
    所有页面都应继承此类，提供统一的布局和样式。
    使用 PySide6-Fluent-Widgets 组件构建现代化 UI。
    
    子类可设置 _lazy_content = True 将 _setup_content() 推迟到首次 showEvent。
    """
    
    _lazy_content: bool = False
    _content_initialized: bool = False

    def __init__(self, title: str, parent: Optional[QWidget] = None, enable_scroll: bool = False):
        """初始化页面
        
        Args:
            title: 页面标题
            parent: 父组件
            enable_scroll: 是否启用全局滚动 (解决小屏幕遮挡问题)
        """
        super().__init__(parent)
        self.title = title
        self.enable_scroll = enable_scroll
        self._content_initialized = False
        self._base_page_timers: dict[str, QTimer] = {}
        self._needs_show_transition = True   # 首次 show 需要过渡动画
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        if self.enable_scroll:
            # 1. 启用滚动：创建根布局包裹 ScrollArea
            self.root_layout = QVBoxLayout(self)
            self.root_layout.setContentsMargins(0, 0, 0, 0)
            self.root_layout.setSpacing(0)
            
            self.scroll_area = ScrollArea(self)
            # 背景透明，边框无
            self.scroll_area.setStyleSheet("QScrollArea {background: transparent; border: none;}")
            self.scroll_area.setWidgetResizable(True)
            self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            
            # 滚动容器
            self.scroll_widget = QWidget()
            self.scroll_widget.setObjectName("scroll_widget")
            self.scroll_widget.setStyleSheet(".QWidget{background: transparent;}")
            
            # 主布局作用于 scroll_widget
            self.main_layout = QVBoxLayout(self.scroll_widget)
            self.main_layout.setContentsMargins(24, 16, 24, 16)
            self.main_layout.setSpacing(16)
            
            self.scroll_area.setWidget(self.scroll_widget)
            self.root_layout.addWidget(self.scroll_area)
        else:
            # 2. 不启用滚动：传统方式
            self.main_layout = QVBoxLayout(self)
            self.main_layout.setContentsMargins(24, 16, 24, 16)
            self.main_layout.setSpacing(16)
        
        # 内容区域布局
        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(12)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        # 使用 stretch 让内容区域可以扩展
        self.main_layout.addLayout(self.content_layout, stretch=1)
    
    def _setup_table_style(self, table):
        """统一设置表格非样式属性。

        注意：setBorderVisible / setBorderRadius 等 Fluent 样式 API 在懒加载 showEvent
        期间（或 Fluent 动画期间）调用会触发 CustomStyleSheetWatcher 递归，导致 C 层崩溃。
        因此本方法仅设置纯属性，不调用任何 Fluent 样式 API。
        边框/圆角由 Fluent TableWidget 的默认值决定（默认已启用边框 + 8px 圆角）。

        Args:
            table: TableWidget 实例
        """
        table.setWordWrap(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        header = table.horizontalHeader()
        if header:
            header.setStretchLastSection(True)
            header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
    
    def show_info(self, title: str, content: str, duration: int = 3000):
        """显示信息提示
        
        Args:
            title: 标题
            content: 内容
            duration: 显示时长（毫秒）
        """
        if FLUENT_WIDGETS_AVAILABLE:
            InfoBar.info(title, content, duration=duration, 
                        position=InfoBarPosition.TOP, parent=self)
    
    def show_success(self, title: str, content: str, duration: int = 3000):
        """显示成功提示
        
        Args:
            title: 标题
            content: 内容
            duration: 显示时长（毫秒）
        """
        if FLUENT_WIDGETS_AVAILABLE:
            InfoBar.success(title, content, duration=duration,
                          position=InfoBarPosition.TOP, parent=self)
    
    def show_warning(self, title: str, content: str, duration: int = 3000):
        """显示警告提示
        
        Args:
            title: 标题
            content: 内容
            duration: 显示时长（毫秒）
        """
        if FLUENT_WIDGETS_AVAILABLE:
            InfoBar.warning(title, content, duration=duration,
                          position=InfoBarPosition.TOP, parent=self)
    
    def show_error(self, title: str, content: str, duration: int = 5000):
        """显示错误提示
        
        Args:
            title: 标题
            content: 内容
            duration: 显示时长（毫秒）
        """
        if FLUENT_WIDGETS_AVAILABLE:
            InfoBar.error(title, content, duration=duration,
                        position=InfoBarPosition.TOP, parent=self)
    
    def _ensure_content(self):
        """确保 _setup_content 已被调用（供延迟初始化使用）"""
        if not self._content_initialized:
            self._content_initialized = True
            t0 = time.perf_counter()
            self._setup_content()
            try:
                from src.utils.startup_profiler import (
                    is_page_load_profiler_enabled,
                    log_page_setup_content_timing,
                )

                if is_page_load_profiler_enabled():
                    label = getattr(self, "title", None) or type(self).__name__
                    log_page_setup_content_timing(str(label), time.perf_counter() - t0)
            except Exception:
                pass

    def _setup_content(self):
        """子类重写此方法构建页面内容。若 _lazy_content=True 则在首次 show 时调用。"""
        pass

    def showEvent(self, event: QShowEvent):
        """页面显示事件，优化切换时的渲染。

        仅在 **真正的页面导航切换** 时冻结并播放淡入动画——通过 hideEvent 置位的
        _needs_show_transition 标记来区分。窗口最大化/还原不经过 hideEvent，
        因此不会触发冻结和动画，避免闪白。

        懒加载内容推迟到 showEvent 返回后的下一个事件循环迭代执行，
        避免在 Fluent stacked_widget 动画期间调用 setStyleSheet 触发 C 层崩溃。
        """
        super().showEvent(event)

        if self._lazy_content and not self._content_initialized:
            self.setUpdatesEnabled(False)
            self._schedule_base_page_timer(
                "ensure_content",
                0,
                self._ensure_content_and_unfreeze,
            )
        elif self._needs_show_transition:
            self._needs_show_transition = False
            self.setUpdatesEnabled(False)
            self._schedule_base_page_timer(
                "unfreeze",
                10,
                self._unfreeze_with_fade,
            )
        # 最大化/还原等窗口状态变化：不冻结、不动画

    def hideEvent(self, event):
        """页面被隐藏（导航切走）时，清理残留动画并标记下次显示需要过渡。"""
        self._cancel_base_page_timer("ensure_content")
        self._cancel_base_page_timer("unfreeze")
        if not self.updatesEnabled():
            self.setUpdatesEnabled(True)
        old_ani = getattr(self, '_page_fade_ani', None)
        if old_ani is not None:
            old_ani.stop()
            self.setGraphicsEffect(None)
            self._page_fade_ani = None
        self._needs_show_transition = True
        super().hideEvent(event)

    def closeEvent(self, event):
        self._cancel_base_page_timers()
        super().closeEvent(event)

    def _schedule_base_page_timer(
        self,
        key: str,
        interval_ms: int,
        callback: Callable[[], None],
    ) -> None:
        self._cancel_base_page_timer(key)
        timer = QTimer(self)
        timer.setSingleShot(True)

        def _fire() -> None:
            self._base_page_timers.pop(key, None)
            timer.deleteLater()
            callback()

        timer.timeout.connect(_fire)
        self._base_page_timers[key] = timer
        timer.start(max(0, interval_ms))

    def _cancel_base_page_timer(self, key: str) -> None:
        timer = self._base_page_timers.pop(key, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()

    def _cancel_base_page_timers(self) -> None:
        for key in list(self._base_page_timers):
            self._cancel_base_page_timer(key)

    def _ensure_content_and_unfreeze(self):
        """构建页面内容后立即解冻更新，消除首次显示时的空白闪烁。"""
        self._ensure_content()
        self._needs_show_transition = False
        if not self._defer_unfreeze:
            self._unfreeze_with_fade()

    @property
    def _defer_unfreeze(self) -> bool:
        """子类重写并返回 True，可推迟 _ensure_content_and_unfreeze 中的解冻操作，
        由子类在异步数据就绪后手动调用 _unfreeze_updates()。"""
        return False

    def _unfreeze_updates(self):
        """在异步数据就绪后由子类调用，解除首次加载时的界面冻结。"""
        if not self.updatesEnabled():
            self._unfreeze_with_fade()

    # ------ 页面淡入动画 ------

    def _unfreeze_with_fade(self):
        """解冻界面并播放一次 opacity 淡入，替代原来生硬的 setUpdatesEnabled 跳变。"""
        self.setUpdatesEnabled(True)
        self._play_fade_in()

    def _play_fade_in(self):
        """对自身播放 opacity 0→1 淡入动画。使用 QGraphicsOpacityEffect 不触发 StyleSheet。"""
        from src.ui.page_animation_prefs import get_page_fade_duration_ms

        fade_ms = get_page_fade_duration_ms()
        if fade_ms <= 0:
            return

        old_ani = getattr(self, '_page_fade_ani', None)
        if old_ani is not None:
            old_ani.stop()
            self.setGraphicsEffect(None)

        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.0)
        self.setGraphicsEffect(effect)

        ani = QPropertyAnimation(effect, b"opacity", self)
        ani.setDuration(fade_ms)
        ani.setStartValue(0.0)
        ani.setEndValue(1.0)
        ani.setEasingCurve(_FADE_EASING)
        ani.finished.connect(lambda: self.setGraphicsEffect(None))
        self._page_fade_ani = ani
        ani.start()
