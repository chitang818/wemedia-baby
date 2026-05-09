"""
Fluent 风格弹窗工具
文件路径：src/ui/utils/fluent_dialogs.py
功能：统一使用 qfluentwidgets MessageBox/MessageBoxBase，保持界面风格一致（不降级 QMessageBox）。
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)
import asyncio

try:
    from qfluentwidgets import BodyLabel, PushButton, SubtitleLabel
    from PySide6.QtWidgets import QWidget, QDialog
    from PySide6.QtCore import Qt
    from src.ui.components.base_dialog import AppMessageBoxBase
    FLUENT_AVAILABLE = True
except ImportError:
    FLUENT_AVAILABLE = False
    AppMessageBoxBase = None  # type: ignore[misc, assignment]
    BodyLabel = None
    PushButton = None
    SubtitleLabel = None
    QWidget = None
    QDialog = None
    Qt = None


def _parent(parent: Optional[QWidget]) -> Optional[QWidget]:
    """获取有效的 parent，避免 None"""
    return parent


def _log_fluent_unavailable(fn: str) -> None:
    logger.error("无法显示 Fluent 弹窗（%s）：qfluentwidgets 或 AppMessageBoxBase 不可用", fn)


def _apply_standard_style(w) -> None:
    if w is None:
        return
    try:
        if hasattr(w, "buttonGroup") and w.buttonGroup is not None:
            w.buttonGroup.setStyleSheet("background-color: transparent; border-top: 1px solid #EDEDED;")
    except Exception:
        pass


def _reorder_confirm_buttons(w) -> None:
    if w is None:
        return
    try:
        lay = getattr(w, "buttonLayout", None)
        if lay is None and hasattr(w, "buttonGroup") and w.buttonGroup is not None:
            lay = w.buttonGroup.layout()
        if lay is not None and lay.indexOf(w.yesButton) >= 0 and lay.indexOf(w.cancelButton) >= 0:
            lay.removeWidget(w.cancelButton)
            lay.removeWidget(w.yesButton)
            lay.addWidget(w.cancelButton)
            lay.addWidget(w.yesButton)
    except Exception:
        pass


if FLUENT_AVAILABLE and AppMessageBoxBase is not None:
    class _SingleButtonDialog(AppMessageBoxBase):
        """符合规范的单按钮提示弹窗（仅"确定"）。"""

        def __init__(self, parent: Optional[QWidget], title: str, content: str):
            super().__init__(parent, header_title=title)
            self.widget.setMinimumWidth(420)

            self.viewLayout.addSpacing(8)

            body = BodyLabel(content, self.widget)
            body.setWordWrap(True)
            self.viewLayout.addWidget(body)

            # 只保留"确定"按钮，隐藏"取消"
            self.yesButton.setText("确定")
            self.cancelButton.hide()

        def keyPressEvent(self, event):
            if Qt is not None and event.key() == Qt.Key.Key_Escape:
                self.reject()
                return
            super().keyPressEvent(event)

    class ConfirmMessageBox(AppMessageBoxBase):
        """符合规范的确认弹窗（取消在左，确定在右）。"""

        def __init__(self, parent: Optional[QWidget], title: str, content: str):
            super().__init__(parent, header_title=title)
            self.widget.setMinimumWidth(420)

            self.viewLayout.addSpacing(8)

            body = BodyLabel(content, self.widget)
            body.setWordWrap(True)
            self.viewLayout.addWidget(body)

            self.yesButton.setText("确定")
            self.cancelButton.setText("取消")
            _apply_standard_style(self)
            _reorder_confirm_buttons(self)

        def keyPressEvent(self, event):
            if Qt is not None and event.key() == Qt.Key.Key_Escape:
                self.reject()
                return
            super().keyPressEvent(event)

    class ForceUpdateMessageBox(AppMessageBoxBase):
        """强制更新：突出当前/新版本对比，分块说明与列表化更新日志，按钮为「前往下载页 / 退出程序」。"""

        def __init__(
            self,
            parent: Optional[QWidget],
            current_version: str,
            remote_version: str,
            notes: str,
        ):
            super().__init__(parent, header_title="需要更新")
            self.widget.setMinimumWidth(480)

            self.viewLayout.addSpacing(12)

            cv = (current_version or "").strip() or "—"
            rv = (remote_version or "").strip() or "—"
            ver = SubtitleLabel(f"当前版本 {cv}　→　新版本 {rv}", self.widget)
            ver.setWordWrap(True)
            self.viewLayout.addWidget(ver)

            self.viewLayout.addSpacing(10)

            summary = BodyLabel(
                "您当前安装的版本已停止支持，无法继续使用。请下载并安装新版本后再启动本程序。",
                self.widget,
            )
            summary.setWordWrap(True)
            self.viewLayout.addWidget(summary)

            note_lines = [ln.strip() for ln in (notes or "").splitlines() if ln.strip()]
            if note_lines:
                self.viewLayout.addSpacing(14)
                self.viewLayout.addWidget(SubtitleLabel("本次更新", self.widget))
                self.viewLayout.addSpacing(6)
                bullet_text = "\n".join(f"• {ln}" for ln in note_lines)
                bl = BodyLabel(bullet_text, self.widget)
                bl.setWordWrap(True)
                self.viewLayout.addWidget(bl)

            self.viewLayout.addSpacing(14)
            tip = BodyLabel(
                "点击「前往下载页」将在浏览器中打开下载地址。"
                "点击「退出程序」、关闭窗口或按 Esc 将直接退出程序。",
                self.widget,
            )
            tip.setWordWrap(True)
            self.viewLayout.addWidget(tip)

            self.yesButton.setText("前往下载页")
            self.cancelButton.setText("退出程序")
            _apply_standard_style(self)
            _reorder_confirm_buttons(self)

        def keyPressEvent(self, event):
            if Qt is not None and event.key() == Qt.Key.Key_Escape:
                self.reject()
                return
            super().keyPressEvent(event)
else:
    _SingleButtonDialog = None  # type: ignore[misc, assignment]
    ConfirmMessageBox = None  # type: ignore[misc, assignment]
    ForceUpdateMessageBox = None  # type: ignore[misc, assignment]


def show_info(parent: Optional[QWidget], title: str, content: str) -> None:
    """Fluent 风格信息提示（仅确定按钮）"""
    if FLUENT_AVAILABLE and _SingleButtonDialog is not None:
        _SingleButtonDialog(_parent(parent), title, content).exec()
        return
    _log_fluent_unavailable("show_info")
    logger.info("%s — %s", title, content)


def show_warning(parent: Optional[QWidget], title: str, content: str) -> None:
    """Fluent 风格警告提示（仅确定按钮）"""
    if FLUENT_AVAILABLE and _SingleButtonDialog is not None:
        _SingleButtonDialog(_parent(parent), title, content).exec()
        return
    _log_fluent_unavailable("show_warning")
    logger.warning("%s — %s", title, content)


def show_error(parent: Optional[QWidget], title: str, content: str) -> None:
    """Fluent 风格错误提示（仅确定按钮）"""
    if FLUENT_AVAILABLE and _SingleButtonDialog is not None:
        _SingleButtonDialog(_parent(parent), title, content).exec()
        return
    _log_fluent_unavailable("show_error")
    logger.error("%s — %s", title, content)


def show_confirm(parent: Optional[QWidget], title: str, content: str) -> bool:
    """Fluent 风格确认框（确定/取消），返回 True 表示点击确定"""
    if FLUENT_AVAILABLE and ConfirmMessageBox is not None:
        w = ConfirmMessageBox(_parent(parent), title, content)
        return bool(w.exec())
    _log_fluent_unavailable("show_confirm")
    logger.info("%s — %s（视为取消）", title, content)
    return False


def show_force_update_confirm(
    parent: Optional[QWidget],
    current_version: str,
    remote_version: str,
    notes: str,
) -> bool:
    """强制更新弹窗。返回 True 表示用户选择「前往下载页」（将打开浏览器）。"""
    if FLUENT_AVAILABLE and ForceUpdateMessageBox is not None:
        w = ForceUpdateMessageBox(_parent(parent), current_version, remote_version, notes)
        return bool(w.exec())
    _log_fluent_unavailable("show_force_update_confirm")
    return False


if FLUENT_AVAILABLE and AppMessageBoxBase is not None:
    class YesNoCancelMessageBox(AppMessageBoxBase):
        """Fluent 风格三按钮确认框：是 / 否 / 取消。exec() 返回 'yes' | 'no' | 'cancel'。"""

        def __init__(self, parent: Optional[QWidget], title: str, content: str):
            super().__init__(parent, header_title=title)
            self._result = "cancel"
            self.widget.setMinimumWidth(420)

            self.viewLayout.addSpacing(8)

            body = BodyLabel(content, self.widget)
            body.setWordWrap(True)
            self.viewLayout.addWidget(body)

            self.yesButton.setText("是")
            self.cancelButton.setText("取消")
            self._no_btn = PushButton("否", self.widget)
            lay = self.buttonGroup.layout()
            if lay is not None:
                lay.insertWidget(1, self._no_btn)
            else:
                self.buttonGroup.addWidget(self._no_btn)
            self.yesButton.clicked.connect(lambda: self._set_result("yes"))
            self._no_btn.clicked.connect(lambda: self._set_result("no"))
            self.cancelButton.clicked.connect(lambda: self._set_result("cancel"))
            _apply_standard_style(self)
            _reorder_confirm_buttons(self)

        def _set_result(self, value: str) -> None:
            self._result = value
            self.accept()

        def keyPressEvent(self, event):
            if Qt is not None and event.key() == Qt.Key.Key_Escape:
                self.reject()
                return
            super().keyPressEvent(event)

        def exec(self) -> str:
            super().exec()
            return self._result

    class ThreeChoiceMessageBox(AppMessageBoxBase):
        """Fluent 风格三按钮确认框（可自定义文案）。exec() 返回 'yes' | 'no' | 'cancel'。"""

        def __init__(
            self,
            parent: Optional[QWidget],
            title: str,
            content: str,
            *,
            yes_text: str,
            no_text: str,
            cancel_text: str = "取消",
            min_width: int = 460,
        ):
            super().__init__(parent, header_title=title)
            self._result = "cancel"
            self.widget.setMinimumWidth(min_width)

            self.viewLayout.addSpacing(8)

            body = BodyLabel(content, self.widget)
            body.setWordWrap(True)
            self.viewLayout.addWidget(body)

            self.yesButton.setText(yes_text)
            self.cancelButton.setText(cancel_text)

            self._no_btn = PushButton(no_text, self.widget)
            lay = self.buttonGroup.layout()
            if lay is not None:
                # 取消在左 / 中间，确定在右；no 按钮放在取消与确定之间
                lay.insertWidget(1, self._no_btn)
            else:
                self.buttonGroup.addWidget(self._no_btn)

            self.yesButton.clicked.connect(lambda: self._set_result("yes"))
            self._no_btn.clicked.connect(lambda: self._set_result("no"))
            self.cancelButton.clicked.connect(lambda: self._set_result("cancel"))
            _apply_standard_style(self)
            _reorder_confirm_buttons(self)

        def _set_result(self, value: str) -> None:
            self._result = value
            self.accept()

        def keyPressEvent(self, event):
            if Qt is not None and event.key() == Qt.Key.Key_Escape:
                self.reject()
                return
            super().keyPressEvent(event)

        def exec(self) -> str:
            super().exec()
            return self._result
else:
    YesNoCancelMessageBox = None  # type: ignore[misc, assignment]
    ThreeChoiceMessageBox = None  # type: ignore[misc, assignment]


def show_yes_no_cancel(parent: Optional[QWidget], title: str, content: str, default: str = "yes") -> str:
    """Fluent 风格三按钮：是 / 否 / 取消。返回 'yes' | 'no' | 'cancel'。"""
    if FLUENT_AVAILABLE and YesNoCancelMessageBox is not None:
        w = YesNoCancelMessageBox(_parent(parent), title, content)
        w.exec()
        return w._result
    _log_fluent_unavailable("show_yes_no_cancel")
    logger.info("%s — %s（default=%s，视为 cancel）", title, content, default)
    return "cancel"


def show_three_choice(
    parent: Optional[QWidget],
    title: str,
    content: str,
    *,
    yes_text: str,
    no_text: str,
    cancel_text: str = "取消",
) -> str:
    """Fluent 风格三按钮：自定义按钮文案。返回 'yes' | 'no' | 'cancel'。"""
    if FLUENT_AVAILABLE and ThreeChoiceMessageBox is not None:
        w = ThreeChoiceMessageBox(
            _parent(parent),
            title,
            content,
            yes_text=yes_text,
            no_text=no_text,
            cancel_text=cancel_text,
        )
        w.exec()
        return w._result
    _log_fluent_unavailable("show_three_choice")
    logger.info("%s — %s（视为 cancel）", title, content)
    return "cancel"


async def show_three_choice_async(
    parent: Optional[QWidget],
    title: str,
    content: str,
    *,
    yes_text: str,
    no_text: str,
    cancel_text: str = "取消",
) -> str:
    """异步三按钮弹窗：避免在 asyncSlot 中 exec() 导致事件循环重入。

    Returns: 'yes' | 'no' | 'cancel'
    """
    if not (FLUENT_AVAILABLE and ThreeChoiceMessageBox is not None and QDialog is not None):
        _log_fluent_unavailable("show_three_choice_async")
        logger.info("%s — %s（视为 cancel）", title, content)
        return "cancel"

    dialog = ThreeChoiceMessageBox(
        _parent(parent),
        title,
        content,
        yes_text=yes_text,
        no_text=no_text,
        cancel_text=cancel_text,
    )
    dialog.setWindowModality(Qt.WindowModality.WindowModal)  # type: ignore[union-attr]

    loop = asyncio.get_event_loop()
    future: asyncio.Future = loop.create_future()

    def on_finished(code: int) -> None:
        if future.done():
            return
        try:
            # ThreeChoiceMessageBox.exec() 会返回 _result，但我们这里用 show()，
            # 因此直接读取 dialog._result（按钮点击时已写入）。
            result = getattr(dialog, "_result", "cancel")
            if code != int(QDialog.DialogCode.Accepted) and result == "cancel":
                future.set_result("cancel")
            else:
                future.set_result(result)
        except Exception as exc:
            future.set_exception(exc)

    dialog.finished.connect(on_finished)
    dialog.show()
    return await future
