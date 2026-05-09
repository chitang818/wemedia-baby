"""
作品简介输入框：字数统计、#话题 高亮、粘贴规范化（与单任务页行为一致）。
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from PySide6.QtCore import QObject, QEvent, QTimer, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QLabel, QTextEdit

from src.domain.publish.work_description.topics import (
    FULLWIDTH_TOPIC_HASH,
    normalize_topics_for_paste,
    parse_topic_list,
    parse_topic_ranges,
)

logger = logging.getLogger(__name__)


class WorkDescriptionEditController(QObject):
    """挂载到 ``QTextEdit`` / ``TextEdit``，统一简介编辑行为。"""

    def __init__(
        self,
        parent: Optional[QObject],
        edit: QTextEdit,
        *,
        char_limit: int = 1000,
        char_count_label: Optional[QLabel] = None,
        topic_count_label: Optional[QLabel] = None,
        topic_count_format: str = "已识别 {} 个话题",
        topic_list_label: Optional[QLabel] = None,
        topic_list_empty_text: str = "（当前未识别到 #话题）",
        topic_list_prefix: str = "话题：",
        topic_list_max_chars: int = 120,
        after_programmatic_text_change: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._edit = edit
        self._char_limit = char_limit
        self._char_count_label = char_count_label
        self._topic_count_label = topic_count_label
        self._topic_count_format = topic_count_format
        self._topic_list_label = topic_list_label
        self._topic_list_empty_text = topic_list_empty_text
        self._topic_list_prefix = topic_list_prefix
        self._topic_list_max_chars = topic_list_max_chars
        self._after_programmatic_text_change = after_programmatic_text_change
        self._last_plain: str = ""

        self._edit.setAcceptRichText(True)
        self._edit.textChanged.connect(self._on_text_changed)
        self._edit.installEventFilter(self)

    def get_plain_text(self) -> str:
        return self._edit.toPlainText()

    def get_topic_tags(self) -> list[str]:
        return parse_topic_list(self.get_plain_text())

    def refresh(self) -> None:
        """强制按当前正文刷新统计与高亮（忽略与 _last_plain 相同短路的场景可传此接口）。"""
        self._last_plain = ""
        self._on_text_changed()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self._edit and event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            # 空格确认话题后刷新高亮（与抖音习惯一致）
            if event.key() == Qt.Key.Key_Space:
                text = self._edit.toPlainText()
                pos = self._edit.textCursor().position()
                text_before = text[:pos]
                if re.search(r"#\S+$", text_before):
                    QTimer.singleShot(0, self._on_text_changed)
            try:
                if event.matches(QKeySequence.StandardKey.Paste):
                    QTimer.singleShot(0, self._normalize_after_paste)
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def _normalize_after_paste(self) -> None:
        try:
            plain = self._edit.toPlainText()
            normalized = normalize_topics_for_paste(plain)
            if normalized == plain:
                return
            cursor = self._edit.textCursor()
            pos = cursor.position()
            self._edit.blockSignals(True)
            try:
                self._edit.setPlainText(normalized)
                cursor.setPosition(min(pos, len(normalized)))
                self._edit.setTextCursor(cursor)
            finally:
                self._edit.blockSignals(False)
            self._last_plain = ""
            self._on_text_changed()
            if self._after_programmatic_text_change is not None:
                self._after_programmatic_text_change(self._edit.toPlainText())
        except Exception as e:
            logger.debug("粘贴话题规范化失败: %s", e)

    def _on_text_changed(self) -> None:
        plain = self._edit.toPlainText()
        # 全角 ＃ 与半角 # 在 QTextEdit 中字符位置一致；替换后高亮区间与 parse_topic_ranges 才能对齐
        if FULLWIDTH_TOPIC_HASH in plain:
            fixed = plain.replace(FULLWIDTH_TOPIC_HASH, "#")
            cursor = self._edit.textCursor()
            pos = cursor.position()
            self._edit.blockSignals(True)
            try:
                self._edit.setPlainText(fixed)
                cursor.setPosition(min(pos, len(fixed)))
                self._edit.setTextCursor(cursor)
            finally:
                self._edit.blockSignals(False)
            self._last_plain = ""
            if self._after_programmatic_text_change is not None:
                self._after_programmatic_text_change(self._edit.toPlainText())
            plain = self._edit.toPlainText()

        if self._char_count_label is not None:
            self._char_count_label.setText(f"{len(plain)} / {self._char_limit}")
        if plain == self._last_plain:
            return

        ranges = parse_topic_ranges(plain)
        tags = parse_topic_list(plain)
        topic_count = len(ranges)

        if self._topic_count_label is not None:
            self._topic_count_label.setText(self._topic_count_format.format(topic_count))

        if self._topic_list_label is not None:
            if not tags:
                self._topic_list_label.setText(self._topic_list_empty_text)
            else:
                joined = "、".join(tags)
                max_c = self._topic_list_max_chars
                if len(joined) > max_c:
                    joined = joined[: max(0, max_c - 1)] + "…"
                self._topic_list_label.setText(f"{self._topic_list_prefix}{joined}")

        self._edit.blockSignals(True)
        try:
            cursor = self._edit.textCursor()
            pos = cursor.position()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.End, QTextCursor.MoveMode.KeepAnchor)
            default_fmt = QTextCharFormat()
            cursor.setCharFormat(default_fmt)
            topic_fmt = QTextCharFormat()
            topic_fmt.setForeground(Qt.GlobalColor.blue)
            topic_fmt.setBackground(Qt.GlobalColor.lightGray)
            for start, end in ranges:
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                cursor.mergeCharFormat(topic_fmt)
            cursor.setPosition(pos)
            self._edit.setTextCursor(cursor)
        finally:
            self._edit.blockSignals(False)
        self._last_plain = plain
