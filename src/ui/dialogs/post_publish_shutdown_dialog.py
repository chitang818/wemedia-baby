"""
发布队列正常结束后：倒计时关机提示弹窗。
文件路径：src/ui/dialogs/post_publish_shutdown_dialog.py
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QDialog, QWidget
from qfluentwidgets import BodyLabel

from src.ui.components.base_dialog import AppMessageBoxBase

logger = logging.getLogger(__name__)

_COUNTDOWN_SEC = 180


def _subprocess_run_kw() -> dict:
    kw: dict = {}
    if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


class PostPublishShutdownDialog(AppMessageBoxBase):
    """提示发布已完成，已排程 3 分钟后关机；可取消。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent, header_title="发布完成")
        self._system_shutdown_scheduled = False
        self._abort_shutdown_done = False
        self._arm_started = False
        self._remaining = _COUNTDOWN_SEC

        self.viewLayout.addSpacing(8)
        self.viewLayout.addWidget(
            BodyLabel("可发布任务已经全部发布完成。", self)
        )
        self._detail_label = BodyLabel("", self)
        self._detail_label.setWordWrap(True)
        self.viewLayout.addWidget(self._detail_label)

        self._countdown_label = BodyLabel("", self)
        self._countdown_label.setWordWrap(True)
        self.viewLayout.addWidget(self._countdown_label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._arm_timer = QTimer(self)
        self._arm_timer.setSingleShot(True)
        self._arm_timer.timeout.connect(self._arm_countdown_and_shutdown)
        self._accept_timer = QTimer(self)
        self._accept_timer.setSingleShot(True)
        self._accept_timer.timeout.connect(self.accept)

        if hasattr(self, "yesButton"):
            self.yesButton.hide()
        if hasattr(self, "cancelButton"):
            self.cancelButton.setText("取消关闭")

        self.widget.setMinimumWidth(460)
        try:
            self._reorder_buttons()
        except Exception:
            pass

    def _reorder_buttons(self) -> None:
        button_layout = getattr(self, "buttonLayout", None)
        if button_layout is None:
            button_layout = self.buttonGroup.layout()
        if button_layout and hasattr(self, "cancelButton"):
            button_layout.removeWidget(self.cancelButton)
            button_layout.addWidget(self.cancelButton)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if event.spontaneous() or self._arm_started:
            return
        self._arm_started = True
        self._arm_timer.start(0)

    def _arm_countdown_and_shutdown(self) -> None:
        if sys.platform != "win32":
            self._detail_label.setText("当前系统不支持自动关机（仅 Windows 可用）。")
            self._countdown_label.setText("")
            return

        try:
            r = subprocess.run(
                [
                    "shutdown",
                    "/s",
                    "/t",
                    str(_COUNTDOWN_SEC),
                    "/c",
                    "媒小宝：发布任务已完成，即将自动关机",
                ],
                capture_output=True,
                timeout=30,
                **_subprocess_run_kw(),
            )
            if r.returncode == 0:
                self._system_shutdown_scheduled = True
                self._detail_label.setText(
                    f"已为本机排程 {_COUNTDOWN_SEC // 60} 分钟后关机；"
                    "点击「取消关闭」或关闭本窗口可中止关机。"
                )
            else:
                err = (r.stderr or r.stdout or b"").decode(errors="replace").strip()
                self._detail_label.setText(
                    "无法排程自动关机（可能被系统策略拒绝）。"
                    + (f" 详情：{err}" if err else "")
                )
                self._countdown_label.setText("")
                logger.warning("shutdown /s 失败 returncode=%s stderr=%s", r.returncode, err)
                return
        except Exception as e:
            self._detail_label.setText(f"排程关机失败：{e}")
            self._countdown_label.setText("")
            logger.warning("排程关机异常: %s", e, exc_info=True)
            return

        self._refresh_countdown_text()
        self._timer.start(1000)

    def _refresh_countdown_text(self) -> None:
        m, s = divmod(max(0, self._remaining), 60)
        self._countdown_label.setText(
            f"倒计时 {m} 分 {s} 秒：若无操作，将在上述时间到达后关闭电脑。"
        )

    def _on_tick(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            self._timer.stop()
            self._countdown_label.setText("已到达预定关机时间，系统将关闭。")
            self._accept_timer.start(800)
            return
        self._refresh_countdown_text()

    def _abort_system_shutdown(self) -> None:
        if not self._system_shutdown_scheduled or self._abort_shutdown_done:
            return
        self._abort_shutdown_done = True
        try:
            subprocess.run(
                ["shutdown", "/a"],
                capture_output=True,
                timeout=30,
                **_subprocess_run_kw(),
            )
        except Exception as e:
            logger.warning("取消关机 shutdown /a 失败: %s", e)

    def done(self, r: int) -> None:
        self._arm_timer.stop()
        self._accept_timer.stop()
        self._timer.stop()
        if r == QDialog.DialogCode.Rejected:
            self._abort_system_shutdown()
        super().done(r)
