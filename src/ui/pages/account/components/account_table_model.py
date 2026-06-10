# -*- coding: utf-8 -*-
"""Model/View data model for account tables."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from src.utils.platform_names import get_platform_display_name


class AccountTableModel(QAbstractTableModel):
    HEADERS = [
        "平台",
        "平台昵称",
        "操作",
        "登录状态",
        "账号组",
        "账号标签",
        "视频库",
        "图文库",
        "已发布最晚时间",
    ]

    COL_PLATFORM = 0
    COL_USERNAME = 1
    COL_ACTION = 2
    COL_LOGIN_STATUS = 3
    COL_GROUP = 4
    COL_TAGS = 5
    COL_VIDEO_STATS = 6
    COL_IMAGE_STATS = 7
    COL_LATEST_PUBLISH = 8

    AccountIdRole = Qt.ItemDataRole.UserRole + 1
    PlatformIdRole = Qt.ItemDataRole.UserRole + 2
    RawRecordRole = Qt.ItemDataRole.UserRole + 3

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._records: List[Dict[str, Any]] = []
        self._row_by_id: Dict[int, int] = {}

    def set_records(self, records: List[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._records = [dict(r) for r in records or []]
        self._row_by_id = {}
        for row, record in enumerate(self._records):
            try:
                self._row_by_id[int(record.get("id"))] = row
            except (TypeError, ValueError):
                continue
        self.endResetModel()

    def records(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._records]

    def update_record(self, account_id: Any, updates: Dict[str, Any]) -> bool:
        row = self.row_for_account_id(account_id)
        if row < 0:
            return False
        self._records[row].update(updates)
        left = self.index(row, 0)
        right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(left, right, [Qt.ItemDataRole.DisplayRole, self.RawRecordRole])
        return True

    def record_at(self, row: int) -> Optional[Dict[str, Any]]:
        if row < 0 or row >= len(self._records):
            return None
        return self._records[row]

    def row_for_account_id(self, account_id: Any) -> int:
        try:
            return self._row_by_id.get(int(account_id), -1)
        except (TypeError, ValueError):
            return -1

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return section + 1 if orientation == Qt.Orientation.Vertical else None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        record = self.record_at(index.row())
        if record is None:
            return None
        col = index.column()
        if role == self.AccountIdRole:
            return record.get("id")
        if role == self.PlatformIdRole:
            return record.get("platform")
        if role == self.RawRecordRole:
            return record
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip_value(record, col)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return self._display_value(record, col)

    def _tooltip_value(self, record: Dict[str, Any], col: int) -> Optional[str]:
        if col == self.COL_LOGIN_STATUS and record.get("publish_risk_state") == "quarantined":
            reason = str(record.get("publish_risk_reason") or "").strip()
            return f"发布风险隔离：{reason}" if reason else "发布风险隔离"
        if col == self.COL_VIDEO_STATS:
            text = self._display_value(record, col)
            return f"视频库：{text}" if text and text != "—" else "视频库：—"
        if col == self.COL_IMAGE_STATS:
            text = self._display_value(record, col)
            return f"图文库：{text}" if text and text != "—" else "图文库：—"
        if col == self.COL_LATEST_PUBLISH:
            text = self._display_value(record, col)
            return text if text and text != "—" else None
        return None

    def _display_value(self, record: Dict[str, Any], col: int) -> str:
        if col == self.COL_PLATFORM:
            return get_platform_display_name(record.get("platform", "") or "")
        if col == self.COL_USERNAME:
            return str(record.get("platform_username") or record.get("account_name") or "未命名")
        if col == self.COL_LOGIN_STATUS:
            if record.get("publish_risk_state") == "quarantined":
                return "风险隔离"
            return "在线" if record.get("login_status") == "online" else "离线"
        if col == self.COL_GROUP:
            group_name = str(record.get("group_name") or "").strip()
            return "" if group_name == "未分类" else group_name
        if col == self.COL_TAGS:
            tags = record.get("tags") or []
            if isinstance(tags, (list, tuple)):
                return ", ".join(str(t) for t in tags if str(t).strip()) or "-"
            return str(tags).strip() or "-"
        if col == self.COL_VIDEO_STATS:
            return str(record.get("_video_stats_text") or "—")
        if col == self.COL_IMAGE_STATS:
            return str(record.get("_image_stats_text") or "—")
        if col == self.COL_LATEST_PUBLISH:
            return str(record.get("latest_publish_time") or record.get("_latest_publish_time") or "—")
        if col == self.COL_ACTION:
            return "打开"
        return ""
