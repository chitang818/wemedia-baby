"""
弹窗基类（标准化规范）
文件路径：src/ui/components/base_dialog.py
功能：提供统一风格、布局和交互的弹窗基类，符合项目标准化规范。
参考：docs/04功能优化方案/弹窗组件标准化规范.md
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget, QHBoxLayout, QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QShowEvent
import logging

try:
    from qfluentwidgets import (
        MessageBoxBase,
        SubtitleLabel,
        BodyLabel,
        TransparentToolButton,
        FluentIcon,
    )

    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False
    from PySide6.QtWidgets import QDialog

    MessageBoxBase = QDialog  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)


def resolve_top_level_window_parent(parent: Optional[QWidget]) -> Optional[QWidget]:
    """将弹窗父控件解析为顶层窗口。

    qfluentwidgets.MaskDialogBase 用父控件宽高铺满半透明遮罩；若 parent 是主窗口内的子页面，
    遮罩只会盖住右侧内容区，左侧导航栏不会变暗。传入页面级控件时应改为 parent.window()。
    """
    if parent is None:
        return None
    top = parent.window()
    return top if top is not None else parent


def install_escape_reject_shortcut(dialog) -> None:
    """子控件获得焦点时，对话框自身的 keyPressEvent 往往收不到 Esc；用 Shortcut 保证一致关闭。

    MaskDialogBase 以主窗口为父、非独立顶层窗口时，WidgetWithChildrenShortcut 在部分场景下不触发；
    使用 ApplicationShortcut 并在回调中校验焦点是否在本对话框子树内，避免误关其它界面。
    """
    if not hasattr(dialog, "reject"):
        return

    def _on_escape() -> None:
        if not dialog.isVisible():
            return
        app = QApplication.instance()
        fw = app.focusWidget() if app is not None else None
        if fw is not None and fw is not dialog and not dialog.isAncestorOf(fw):
            return
        dialog.reject()

    sc = QShortcut(QKeySequence(Qt.Key.Key_Escape), dialog)
    sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
    sc.activated.connect(_on_escape)


def install_dialog_close_button(dialog, header_title: Optional[str] = None) -> None:
    """在 MessageBoxBase 内容卡片顶部插入标题栏：左侧可选标题、右侧关闭（等价于取消/ESC）。

    可安全重复调用，内部会去重。用于无法改为继承 AppMessageBoxBase 的临时实例（如 MessageBoxBase(parent)）。
    """
    if getattr(dialog, "_wmb_close_button_installed", False):
        return
    vbox = getattr(dialog, "vBoxLayout", None)
    card = getattr(dialog, "widget", None)
    if vbox is None or card is None:
        return
    try:
        header = QWidget(card)
        h = QHBoxLayout(header)
        # 与 MessageBoxBase.viewLayout 左右边距 24 对齐，标题与正文左缘一线
        if header_title and FLUENT_WIDGETS_AVAILABLE:
            h.setContentsMargins(24, 18, 12, 8)
            h.setSpacing(8)
            tl = SubtitleLabel(header_title, header)
            h.addWidget(tl, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            # 与正文区标题分离：顶栏标题仍用 titleLabel 命名，便于 AccountSelectionDialog 等 setText
            dialog.titleLabel = tl
        else:
            h.setContentsMargins(4, 4, 4, 0)
            h.setSpacing(0)
        h.addStretch(1)
        btn = TransparentToolButton(FluentIcon.CLOSE, header)
        btn.setFixedSize(32, 32)
        btn.setToolTip("关闭")
        btn.clicked.connect(dialog.reject)
        h.addWidget(btn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        vbox.insertWidget(0, header, 0)
        dialog._wmb_close_button_installed = True
    except Exception:
        logger.debug("install_dialog_close_button 失败", exc_info=True)


if FLUENT_WIDGETS_AVAILABLE:

    class AppMessageBoxBase(MessageBoxBase):
        """项目统一弹窗基类：顶栏左侧标题（可选 header_title）+ 右上角关闭按钮，与规范一致。"""

        def __init__(self, parent=None, *, header_title: Optional[str] = None):
            super().__init__(resolve_top_level_window_parent(parent))
            install_dialog_close_button(self, header_title=header_title)
            install_escape_reject_shortcut(self)
            # 嵌入主窗口的 MaskDialog 用 show() 打开时焦点常留在背后页面，导致 ESC 等快捷键不生效
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        def showEvent(self, event: QShowEvent) -> None:
            super().showEvent(event)
            if event.spontaneous():
                return
            QTimer.singleShot(0, self._wmb_activate_modal_focus)

        def _wmb_activate_modal_focus(self) -> None:
            if not self.isVisible():
                return
            top = self.window()
            if top is not None:
                top.activateWindow()
            cb = getattr(self, "cancelButton", None)
            if cb is not None and cb.isVisible() and cb.isEnabled():
                cb.setFocus(Qt.FocusReason.PopupFocusReason)
                return
            yb = getattr(self, "yesButton", None)
            if yb is not None and yb.isVisible() and yb.isEnabled():
                yb.setFocus(Qt.FocusReason.PopupFocusReason)
                return
            card = getattr(self, "widget", None)
            if card is not None:
                card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                card.setFocus(Qt.FocusReason.PopupFocusReason)
                return
            self.setFocus(Qt.FocusReason.PopupFocusReason)

        def keyPressEvent(self, event):
            # 显式 Esc 关闭，避免焦点在子控件上时仅依赖 QDialog 默认行为不可靠
            if event.key() == Qt.Key.Key_Escape:
                self.reject()
                return
            super().keyPressEvent(event)

else:

    class _AppMessageBoxBaseFallback(MessageBoxBase):  # type: ignore[misc, valid-type]
        """无 Fluent 时占位：忽略 header_title，避免子类 super 传参报错。"""

        def __init__(self, parent=None, *, header_title: Optional[str] = None):
            super().__init__(resolve_top_level_window_parent(parent))
            install_escape_reject_shortcut(self)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        def showEvent(self, event: QShowEvent) -> None:
            super().showEvent(event)
            if event.spontaneous():
                return
            QTimer.singleShot(0, self._wmb_activate_modal_focus)

        def _wmb_activate_modal_focus(self) -> None:
            if not self.isVisible():
                return
            top = self.window()
            if top is not None:
                top.activateWindow()
            self.setFocus(Qt.FocusReason.PopupFocusReason)

        def keyPressEvent(self, event):
            if event.key() == Qt.Key.Key_Escape:
                self.reject()
                return
            super().keyPressEvent(event)

    AppMessageBoxBase = _AppMessageBoxBaseFallback  # type: ignore[misc, assignment]


class StandardBaseDialog(AppMessageBoxBase):
    """标准化弹窗基类

    提供统一的标题、按钮排序、ESC 关闭等基础能力。
    子类只需关注业务 UI 构建，无需重复处理规范性逻辑。
    """

    def __init__(self, parent=None, title="提示"):
        super().__init__(parent, header_title=title)

        if not FLUENT_WIDGETS_AVAILABLE:
            self.setWindowTitle(title)
            return

        self.widget.setMinimumWidth(400)
        # titleLabel 由顶栏 install_dialog_close_button 创建，勿再放入 viewLayout

        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self._reorder_buttons()

    def _reorder_buttons(self):
        """取消在左，确定在右"""
        if not FLUENT_WIDGETS_AVAILABLE:
            return
        button_layout = getattr(self, "buttonLayout", None)
        if button_layout is None:
            button_layout = self.buttonGroup.layout()
        if button_layout:
            button_layout.removeWidget(self.yesButton)
            button_layout.removeWidget(self.cancelButton)
            button_layout.addWidget(self.cancelButton)
            button_layout.addWidget(self.yesButton)

    def add_description(self, text: str):
        """添加一段灰色说明文本"""
        if not FLUENT_WIDGETS_AVAILABLE:
            return None
        desc = BodyLabel(text, self.widget)
        desc.setTextColor('#999999', '#999999')
        self.viewLayout.addWidget(desc)
        return desc

    def add_widget(self, widget: QWidget):
        """向弹窗内容区添加自定义组件"""
        if not FLUENT_WIDGETS_AVAILABLE:
            return
        self.viewLayout.addWidget(widget)

    def set_yes_button_text(self, text: str):
        if FLUENT_WIDGETS_AVAILABLE:
            self.yesButton.setText(text)

    def set_cancel_button_text(self, text: str):
        if FLUENT_WIDGETS_AVAILABLE:
            self.cancelButton.setText(text)
