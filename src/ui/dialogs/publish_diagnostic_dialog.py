"""
发布失败诊断提示弹窗。
文件路径：src/ui/dialogs/publish_diagnostic_dialog.py
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, InfoBar, LineEdit, PushButton

from src.ui.components.base_dialog import AppMessageBoxBase

logger = logging.getLogger(__name__)

_HEADER_TITLE = "发布失败 · 已保存诊断信息"
_INSTRUCTION_TEXT = (
    "软件已保存失败时的页面截图与页面结构信息。\n"
    "如需反馈问题，可将诊断文件夹发给开发者，用于排查平台页面变化。"
)
_FALLBACK_ERROR = "详见发布日志"


def format_elided_diagnostic_path(path: str, *, max_len: int = 72) -> str:
    """生成弹窗内展示的省略路径（中间段用 … 表示）。"""
    normalized = (path or "").strip()
    if not normalized:
        return ""
    parts = Path(normalized).parts
    if len(parts) <= 2:
        return normalized
    compact = f"…\\{parts[-3]}\\{parts[-2]}\\{parts[-1]}" if len(parts) >= 3 else f"…\\{parts[-2]}\\{parts[-1]}"
    if len(compact) <= max_len:
        return compact
    head = compact[: max_len // 2 - 1]
    tail = compact[-(max_len // 2 - 2) :]
    return f"{head}…{tail}"


class PublishDiagnosticDialog(AppMessageBoxBase):
    """发布失败后的诊断包提示：分层展示原因、省略路径与明确操作按钮。"""

    def __init__(
        self,
        parent: Optional[QWidget],
        *,
        diagnostic_path: str,
        error_message: Optional[str] = None,
        on_open_folder: Optional[Callable[[str], None]] = None,
        platform: str = "",
        analysis_hints: Optional[Sequence[str]] = None,
    ):
        super().__init__(parent, header_title=_HEADER_TITLE)
        self._diagnostic_path = (diagnostic_path or "").strip()
        self._on_open_folder = on_open_folder
        self._platform = (platform or "").strip().lower()
        self._analysis_hints = [
            str(h).strip() for h in (analysis_hints or []) if str(h).strip()
        ]

        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self.widget.setMinimumWidth(440)
        self.widget.setMaximumWidth(480)

        self.viewLayout.addSpacing(8)

        self.viewLayout.addWidget(CaptionLabel("失败原因", self.widget))
        reason_text = (error_message or "").strip() or _FALLBACK_ERROR
        reason_label = BodyLabel(reason_text, self.widget)
        reason_label.setWordWrap(True)
        self.viewLayout.addWidget(reason_label)

        if self._platform == "xiaohongshu" and self._analysis_hints:
            self.viewLayout.addSpacing(8)
            self.viewLayout.addWidget(CaptionLabel("页面结构提示（小红书）", self.widget))
            for hint in self._analysis_hints[:5]:
                hint_label = BodyLabel(f"· {hint}", self.widget)
                hint_label.setWordWrap(True)
                self.viewLayout.addWidget(hint_label)

        self.viewLayout.addSpacing(10)

        summary = BodyLabel(_INSTRUCTION_TEXT, self.widget)
        summary.setWordWrap(True)
        self.viewLayout.addWidget(summary)

        self.viewLayout.addSpacing(10)

        self.viewLayout.addWidget(CaptionLabel("诊断文件夹", self.widget))
        path_edit = LineEdit(self.widget)
        path_edit.setReadOnly(True)
        path_edit.setText(format_elided_diagnostic_path(self._diagnostic_path))
        path_edit.setToolTip(self._diagnostic_path)
        path_edit.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.viewLayout.addWidget(path_edit)

        self.viewLayout.addSpacing(8)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        open_btn = PushButton("打开文件夹", self.widget)
        copy_btn = PushButton("复制路径", self.widget)
        open_btn.clicked.connect(self._copy_open_folder)
        copy_btn.clicked.connect(self._copy_path_to_clipboard)
        action_row.addWidget(open_btn)
        action_row.addWidget(copy_btn)
        action_row.addStretch(1)
        action_host = QWidget(self.widget)
        action_host.setLayout(action_row)
        self.viewLayout.addWidget(action_host)

        if hasattr(self, "cancelButton"):
            self.cancelButton.hide()
        if hasattr(self, "yesButton"):
            self.yesButton.setText("知道了")

        try:
            if hasattr(self, "buttonGroup") and self.buttonGroup is not None:
                self.buttonGroup.setStyleSheet(
                    "background-color: transparent; border-top: 1px solid #EDEDED;"
                )
        except Exception:
            pass

    def _dialog_parent(self) -> QWidget:
        return self.window() or self.widget

    def _copy_open_folder(self) -> None:
        if self._on_open_folder is not None:
            self._on_open_folder(self._diagnostic_path)
            return
        logger.debug("PublishDiagnosticDialog: on_open_folder not set")

    def _copy_path_to_clipboard(self) -> None:
        path = self._diagnostic_path
        parent = self._dialog_parent()
        if not path:
            InfoBar.warning("无法复制", "诊断路径为空。", parent=parent)
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            InfoBar.warning("无法复制", "系统剪贴板不可用。", parent=parent)
            return
        clipboard.setText(path)
        InfoBar.success("已复制", "诊断文件夹完整路径已复制到剪贴板。", parent=parent, duration=3000)
