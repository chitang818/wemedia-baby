"""
任务说明卡片
文件路径：src/ui/components/task_description_card.py
功能：发布列表页底部展示当前选中任务详情；状态以标题栏徽章为准，正文区不重复「发布中/失败」等状态句
"""

from __future__ import annotations

import html
from typing import Optional, Dict, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QTextEdit,
    QScrollArea,
    QSizePolicy,
)

try:
    from qfluentwidgets import StrongBodyLabel

    _FLUENT = True
except ImportError:
    _FLUENT = False
    StrongBodyLabel = None  # type: ignore[misc, assignment]

from src.utils.platform_names import get_platform_display_name
from src.ui.pages.publish.task_field_display import task_field_str_or_dash


def _status_zh(status: str) -> str:
    m = {
        "pending": "待发布",
        "running": "发布中",
        "success": "成功",
        "failed": "失败",
    }
    return m.get(status or "", status or "—")


_STATUS_BADGE_TEXT = {
    "pending": "⏳ 待发布",
    "running": "▶ 发布中",
    "success": "✅ 成功",
    "failed": "❌ 失败",
}


def _format_scheduled_time(raw: Any) -> str:
    if raw is None:
        return ""
    if hasattr(raw, "strftime"):
        try:
            return raw.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(raw).strip()
    s = str(raw).strip()
    return s


class TaskDescriptionCard(QFrame):
    """任务说明卡片：展示任务状态与关键内容。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("TaskDescriptionCard")
        lay = QVBoxLayout(self)
        # 与 LogDisplayWidget（发布日志）一致
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        if _FLUENT and StrongBodyLabel is not None:
            title = StrongBodyLabel("任务说明", self)
        else:
            title = QLabel("任务说明", self)
            title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        title.setObjectName("UnifiedCardTitle")
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        self._status_badge = QLabel(self)
        self._status_badge.setObjectName("TaskDescriptionStatusBadge")
        self._status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self._status_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(header_layout)

        self._panel = QFrame(self)
        self._panel.setObjectName("TaskDescriptionPanel")
        panel_lay = QVBoxLayout(self._panel)
        panel_lay.setContentsMargins(10, 10, 10, 10)
        panel_lay.setSpacing(0)

        self._scroll = QScrollArea(self._panel)
        self._scroll.setObjectName("TaskDescriptionScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        inner = QWidget()
        inner.setObjectName("TaskDescriptionScrollInner")
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(4)

        self._fail_banner = QFrame(inner)
        self._fail_banner.setObjectName("TaskDescriptionFailBanner")
        fail_lay = QHBoxLayout(self._fail_banner)
        fail_lay.setContentsMargins(12, 10, 12, 10)
        fail_lay.setSpacing(10)
        self._fail_icon = QLabel(self._fail_banner)
        self._fail_icon.setObjectName("TaskDescriptionFailIcon")
        self._fail_icon.setText("⚠")
        self._fail_icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self._fail_message = QLabel(self._fail_banner)
        self._fail_message.setObjectName("TaskDescriptionFailMessage")
        self._fail_message.setWordWrap(True)
        self._fail_message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fail_lay.addWidget(self._fail_icon, 0, Qt.AlignmentFlag.AlignTop)
        fail_lay.addWidget(self._fail_message, 1)
        self._fail_banner.hide()

        self._summary_label = QLabel(inner)
        self._summary_label.setObjectName("TaskDescriptionSummary")
        self._summary_label.setWordWrap(True)

        self._extra_label = QLabel(inner)
        self._extra_label.setObjectName("TaskDescriptionExtra")
        self._extra_label.setWordWrap(True)
        self._extra_label.setOpenExternalLinks(True)
        self._extra_label.hide()

        self._section_title = QLabel("任务信息", inner)
        self._section_title.setObjectName("TaskDescriptionSectionTitle")

        self._grid_host = QWidget(inner)
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(8)
        self._grid.setColumnStretch(1, 1)
        self._grid.setColumnMinimumWidth(0, 72)

        self._content_title = QLabel("内容", inner)
        self._content_title.setObjectName("TaskDescriptionBodyTitle")

        self._body = QTextEdit(inner)
        self._body.setObjectName("TaskDescriptionBody")
        self._body.setReadOnly(True)
        self._body.setPlaceholderText("暂无描述或标题")
        self._body.setMinimumHeight(72)
        self._body.setFont(QFont("Microsoft YaHei", 12))
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

        inner_lay.addWidget(self._fail_banner)
        inner_lay.addWidget(self._summary_label)
        inner_lay.addWidget(self._extra_label)
        inner_lay.addWidget(self._section_title)
        inner_lay.addWidget(self._grid_host)
        inner_lay.addWidget(self._content_title)
        inner_lay.addWidget(self._body, 1)

        self._scroll.setWidget(inner)
        self._scroll.setMinimumHeight(120)
        panel_lay.addWidget(self._scroll, 1)
        lay.addWidget(self._panel, 1)

        self.clear()

    def _polish_badge(self):
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

    def _set_badge(self, text: str, kind: str):
        self._status_badge.setText(text)
        self._status_badge.setProperty("status_kind", kind)
        self._polish_badge()

    def _polish_extra(self):
        self._extra_label.style().unpolish(self._extra_label)
        self._extra_label.style().polish(self._extra_label)

    def _set_extra(self, text: str, kind: str):
        if not (text or "").strip():
            self._extra_label.hide()
            self._extra_label.clear()
            self._extra_label.setToolTip("")
            return
        self._extra_label.setProperty("extra_kind", kind)
        if kind == "link":
            self._extra_label.setTextFormat(Qt.TextFormat.RichText)
            self._extra_label.setText(text)
        else:
            self._extra_label.setTextFormat(Qt.TextFormat.PlainText)
            self._extra_label.setText(text)
        self._polish_extra()
        self._extra_label.show()

    def _clear_grid(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _add_grid_row(self, row: int, key: str, value: str) -> None:
        kl = QLabel(key)
        kl.setObjectName("TaskDescriptionKVKey")
        kl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        vl = QLabel(value)
        vl.setObjectName("TaskDescriptionKVVal")
        vl.setWordWrap(True)
        vl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._grid.addWidget(kl, row, 0)
        self._grid.addWidget(vl, row, 1)

    def clear(self):
        self._set_badge("—", "none")
        self._fail_banner.hide()
        self._fail_message.clear()
        self._summary_label.setText("点击任务列表中的一条任务，在此查看状态与详情。")
        self._summary_label.show()
        self._set_extra("", "none")
        self._clear_grid()
        self._section_title.hide()
        self._grid_host.hide()
        self._content_title.hide()
        self._body.hide()
        self._body.clear()
        self._body.setPlaceholderText("")

    def set_task(self, record: Optional[Dict[str, Any]]):
        if not record:
            self.clear()
            return

        status = (record.get("status") or "").strip()
        if status in _STATUS_BADGE_TEXT:
            self._set_badge(_STATUS_BADGE_TEXT[status], status)
        else:
            self._set_badge(_status_zh(status), "none")

        platform_raw = (record.get("platform") or "").strip()
        platform_display = task_field_str_or_dash(
            get_platform_display_name(platform_raw) if platform_raw else ""
        )
        account = task_field_str_or_dash(record.get("platform_username"))
        file_path = task_field_str_or_dash(record.get("file_path"))
        sched_str = _format_scheduled_time(record.get("scheduled_publish_time"))
        is_scheduled = bool(sched_str)
        desc = record.get("description") or record.get("title") or ""

        error_msg = (record.get("error_message") or record.get("error") or "").strip()

        self._fail_banner.hide()
        self._fail_message.clear()

        if status == "pending":
            # 与状态徽章重复，不展示摘要行
            self._summary_label.clear()
            self._summary_label.hide()
        elif status == "running":
            self._summary_label.clear()
            self._summary_label.hide()
        elif status == "success":
            # 徽章已表示成功；仅在有链接时展示快捷入口
            self._summary_label.clear()
            self._summary_label.hide()
            pub_url = (record.get("publish_url") or "").strip()
            if pub_url:
                u = html.escape(pub_url)
                self._set_extra(f'<a href="{u}">打开发布链接</a>', "link")
                self._extra_label.setToolTip(pub_url)
            else:
                self._set_extra("", "none")
                self._extra_label.setToolTip("")
        elif status == "failed":
            # 徽章已表示失败；仅展示失败原因（醒目横幅）
            self._summary_label.clear()
            self._summary_label.hide()
            self._set_extra("", "none")
            self._extra_label.setToolTip("")
            reason = error_msg if error_msg else "（未记录具体原因）"
            self._fail_message.setText(reason)
            self._fail_banner.show()
        else:
            self._summary_label.show()
            self._summary_label.setText("当前任务信息如下。")

        if status != "success" and status != "failed":
            self._set_extra("", "none")
        elif status == "success" and not (record.get("publish_url") or "").strip():
            self._set_extra("", "none")

        self._section_title.show()
        self._grid_host.show()
        self._content_title.show()
        self._body.show()
        self._body.setPlaceholderText("暂无描述或标题")

        self._clear_grid()
        row = 0
        if is_scheduled:
            self._add_grid_row(row, "发布方式", "定时发布")
            row += 1
            self._add_grid_row(row, "计划时间", sched_str)
            row += 1
        else:
            self._add_grid_row(row, "发布方式", "立即发布")
            row += 1

        self._add_grid_row(row, "平台", platform_display)
        row += 1
        self._add_grid_row(row, "账号", account)
        row += 1
        self._add_grid_row(row, "文件", file_path)
        row += 1
        if platform_raw in ("wechat_video", "douyin", "kuaishou"):
            try:
                from src.domain.publish.work_declaration import format_work_declaration_table_cell

                wd = format_work_declaration_table_cell(
                    platform_raw, record.get("privacy_settings"), empty_display="—",
                )
            except Exception:
                wd = "—"
            self._add_grid_row(row, "作品申明", wd)
            row += 1

        self._body.setPlainText(task_field_str_or_dash(desc))
