# -*- coding: utf-8 -*-
"""Model/View data model for publish record tables."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from src.domain.publish.work_declaration import format_work_declaration_table_cell
from src.ui.pages.publish.poi_info_display import format_poi_table_cell_display
from src.ui.pages.publish.task_field_display import (
    TASK_FIELD_EMPTY_DISPLAY,
    format_cart_info_table_cell,
    task_field_str_or_dash,
)
from src.utils.date_utils import format_schedule_time_st_str
from src.utils.platform_names import get_platform_display_name


def _record_is_image_task(record: Dict[str, Any]) -> bool:
    file_type = (record.get("file_type") or record.get("task_type") or "").strip().lower()
    if file_type == "image":
        return True
    if file_type == "video":
        return False
    file_path = str(record.get("file_path") or "")
    paths = [p.strip().lower() for p in file_path.split(",") if p.strip()]
    return any(p.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")) for p in paths)


def _format_timestamp(value: Any) -> str:
    if value is None:
        return "-"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).replace("T", " ")
    return text[:19] if text else "-"


def _file_name_display(file_path: str) -> str:
    if not file_path:
        return ""
    first = file_path.split(",")[0].strip()
    if first.startswith("__FOLDER__:"):
        first = first[len("__FOLDER__:") :]
    if first == "__DELETED__":
        return "已删除"
    return os.path.basename(first.rstrip("/\\")) or first


def _folder_display(file_path: str) -> str:
    if not file_path:
        return ""
    first = file_path.split(",")[0].strip()
    if first.startswith("__FOLDER__:"):
        first = first[len("__FOLDER__:") :]
    if first == "__DELETED__":
        return "已删除"
    try:
        return os.path.dirname(os.path.abspath(os.path.normpath(first)))
    except Exception:
        return first


def _music_display(record: Dict[str, Any]) -> str:
    if not _record_is_image_task(record):
        return TASK_FIELD_EMPTY_DISPLAY
    raw = (record.get("music_info") or "").strip()
    if not raw:
        return TASK_FIELD_EMPTY_DISPLAY
    try:
        data = json.loads(raw)
        if data.get("music_type") == "random":
            return "随机"
        return data.get("music_name") or data.get("name") or data.get("title") or "已设置"
    except Exception:
        return "已设置"

def _recycle_source_label(status: str) -> str:
    if status == "deleted_success":
        return "已发布"
    return "待发布"


def _recycle_status_display(status: str) -> str:
    if status == "deleted_pending":
        return "回收（原待发布）"
    if status == "deleted_success":
        return "回收（原已发布）"
    status = (status or "").strip()
    return status if status else TASK_FIELD_EMPTY_DISPLAY


class PublishRecordTableModel(QAbstractTableModel):
    COL_CREATE_TIME = 0
    COL_TYPE = 1
    COL_PLATFORM = 2
    COL_ACCOUNT_GROUP = 3
    COL_TASK_SOURCE = 4
    COL_ACCOUNT_NAME = 5
    COL_FILE = 6
    COL_COVER = 7
    COL_TITLE = 8
    COL_DESCRIPTION = 9
    COL_SCHEDULED_TIME = 10
    COL_ORIGINAL = 11
    COL_MUSIC = 12
    COL_CART = 13
    COL_GROUP_BUY = 14
    COL_LOCATION = 15
    COL_STATUS = 16
    COL_FILE_LOCATION = 17
    COL_ACTION = 18

    HEADERS = [
        "创建时间",
        "类型",
        "平台",
        "账号组",
        "任务源",
        "平台昵称",
        "文件/文件夹",
        "封面",
        "作品标题",
        "作品描述",
        "定时时间",
        "作品声明",
        "音乐",
        "购物车",
        "团购",
        "位置",
        "状态",
        "文件位置",
        "操作",
    ]

    RECYCLE_HEADERS = [
        "创建时间",
        "类型",
        "平台",
        "账号组",
        "任务源",
        "平台昵称",
        "文件/文件夹",
        "封面",
        "作品标题",
        "作品描述",
        "发布时间",
        "作品声明",
        "购物车",
        "团购",
        "位置",
        "状态",
        "文件位置",
        "来源",
        "操作",
    ]

    RecordIdRole = Qt.ItemDataRole.UserRole + 1
    RawRecordRole = Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._records: List[Dict[str, Any]] = []
        self._row_by_id: Dict[int, int] = {}
        self._cell_overrides: Dict[Tuple[int, int], str] = {}
        self._success_page: bool = False
        self._action_text: str = "编辑"
        self._recycle_page: bool = False

    def set_recycle_page(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._recycle_page == enabled:
            return
        self._recycle_page = enabled
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)
        if self.rowCount() > 0:
            top = self.index(0, 0)
            bottom = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole])

    def set_success_page(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._success_page == enabled:
            return
        self._success_page = enabled
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, self.COL_CREATE_TIME, self.COL_CREATE_TIME)
        if self.rowCount() > 0:
            top = self.index(0, self.COL_CREATE_TIME)
            bottom = self.index(self.rowCount() - 1, self.COL_CREATE_TIME)
            self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.DisplayRole])

    def set_action_text(self, text: str) -> None:
        text = str(text or "编辑")
        if self._action_text == text:
            return
        self._action_text = text
        if self.rowCount() > 0:
            top = self.index(0, self.COL_ACTION)
            bottom = self.index(self.rowCount() - 1, self.COL_ACTION)
            self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.DisplayRole])

    def set_records(
        self,
        records: List[Dict[str, Any]],
        *,
        success_page: Optional[bool] = None,
        action_text: Optional[str] = None,
        recycle_page: Optional[bool] = None,
    ) -> None:
        self.beginResetModel()
        if recycle_page is not None:
            self._recycle_page = bool(recycle_page)
        if success_page is not None:
            self._success_page = bool(success_page)
        if action_text is not None:
            self._action_text = str(action_text or "编辑")
        self._records = [dict(r) for r in records or []]
        self._cell_overrides = {}
        self._rebuild_index()
        self.endResetModel()

    def records(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._records]

    def update_record(self, record_id: Any, updates: Dict[str, Any]) -> bool:
        row = self.row_for_record_id(record_id)
        if row < 0:
            return False
        self._records[row].update(updates)
        left = self.index(row, 0)
        right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(left, right, [Qt.ItemDataRole.DisplayRole, self.RawRecordRole])
        return True

    def set_cell_text(self, record_id: Any, column: int, text: str) -> bool:
        row = self.row_for_record_id(record_id)
        if row < 0:
            return False
        try:
            rid = int(record_id)
        except (TypeError, ValueError):
            return False
        self._cell_overrides[(rid, int(column))] = str(text)
        idx = self.index(row, int(column))
        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DisplayRole])
        return True

    def remove_record_at(self, row: int) -> bool:
        if row < 0 or row >= len(self._records):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        record = self._records.pop(row)
        try:
            rid = int(record.get("id"))
        except (TypeError, ValueError):
            rid = None
        if rid is not None:
            self._cell_overrides = {
                key: value for key, value in self._cell_overrides.items() if key[0] != rid
            }
        self._rebuild_index()
        self.endRemoveRows()
        return True

    def record_at(self, row: int) -> Optional[Dict[str, Any]]:
        if row < 0 or row >= len(self._records):
            return None
        return self._records[row]

    def row_for_record_id(self, record_id: Any) -> int:
        try:
            return self._row_by_id.get(int(record_id), -1)
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
            if self._recycle_page:
                return self.RECYCLE_HEADERS[section]
            if section == self.COL_CREATE_TIME and self._success_page:
                return "发布时间"
            return self.HEADERS[section]
        return section + 1 if orientation == Qt.Orientation.Vertical else None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        record = self.record_at(index.row())
        if record is None:
            return None
        if role == self.RecordIdRole:
            return record.get("id")
        if role == self.RawRecordRole:
            return record
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() == self.COL_FILE_LOCATION or (self._recycle_page and index.column() == self.COL_STATUS):
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip_value(record, index.column())
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        try:
            rid = int(record.get("id"))
        except (TypeError, ValueError):
            rid = None
        if rid is not None:
            override = self._cell_overrides.get((rid, index.column()))
            if override is not None:
                return override
        return self._display_value(record, index.column())

    def _display_value(self, record: Dict[str, Any], col: int) -> str:
        if self._recycle_page:
            return self._recycle_display_value(record, col)
        if col == self.COL_CREATE_TIME:
            value = (record.get("updated_at") or record.get("created_at")) if self._success_page else record.get("created_at")
            return _format_timestamp(value)
        if col == self.COL_TYPE:
            return "图文" if _record_is_image_task(record) else "视频"
        if col == self.COL_PLATFORM:
            return task_field_str_or_dash(get_platform_display_name(record.get("platform", "") or ""))
        if col == self.COL_ACCOUNT_GROUP:
            return str(record.get("account_group_name") or "").strip() or TASK_FIELD_EMPTY_DISPLAY
        if col == self.COL_TASK_SOURCE:
            task_source = record.get("task_source") or ""
            return "账号组" if task_source == "group" else ("账号" if task_source == "account" else TASK_FIELD_EMPTY_DISPLAY)
        if col == self.COL_ACCOUNT_NAME:
            return task_field_str_or_dash(record.get("platform_username"))
        if col == self.COL_FILE:
            return task_field_str_or_dash(record.get("_file_display") or _file_name_display(record.get("file_path") or ""))
        if col == self.COL_COVER:
            return "本地封面" if record.get("cover_path") else "首帧封面"
        if col == self.COL_TITLE:
            return task_field_str_or_dash(record.get("title"))
        if col == self.COL_DESCRIPTION:
            return task_field_str_or_dash(record.get("description"))
        if col == self.COL_SCHEDULED_TIME:
            return format_schedule_time_st_str(record.get("scheduled_publish_time")) or "立即发布"
        if col == self.COL_ORIGINAL:
            try:
                full = format_work_declaration_table_cell(
                    (record.get("platform") or "").strip(),
                    record.get("privacy_settings"),
                    empty_display=TASK_FIELD_EMPTY_DISPLAY,
                )
            except Exception:
                full = TASK_FIELD_EMPTY_DISPLAY
            return full
        if col == self.COL_MUSIC:
            return _music_display(record)
        if col == self.COL_CART:
            return format_cart_info_table_cell((record.get("cart_info") or "").strip())
        if col == self.COL_GROUP_BUY:
            return "已设置" if (record.get("anchor_info") or "").strip() else TASK_FIELD_EMPTY_DISPLAY
        if col == self.COL_LOCATION:
            return format_poi_table_cell_display(
                record.get("poi_info"),
                platform=(record.get("platform") or "").strip(),
                wechat_empty_location_open_picker=record.get("wechat_empty_location_open_picker"),
            )
        if col == self.COL_STATUS:
            status = (record.get("status") or "").strip()
            return {
                "success": "✅ 成功",
                "failed": "❌ 失败",
                "pending": "⏳ 待发布",
            }.get(status, status) if status else TASK_FIELD_EMPTY_DISPLAY
        if col == self.COL_FILE_LOCATION:
            return task_field_str_or_dash(record.get("_folder_display") or _folder_display(record.get("file_path") or ""))
        if col == self.COL_ACTION:
            return self._action_text
        return ""

    def _recycle_display_value(self, record: Dict[str, Any], col: int) -> str:
        if col == self.COL_CREATE_TIME:
            return _format_timestamp(record.get("created_at"))
        if col == self.COL_TYPE:
            return "图文" if _record_is_image_task(record) else "视频"
        if col == self.COL_PLATFORM:
            return task_field_str_or_dash(get_platform_display_name(record.get("platform", "") or ""))
        if col == self.COL_ACCOUNT_GROUP:
            return str(record.get("account_group_name") or "").strip() or TASK_FIELD_EMPTY_DISPLAY
        if col == self.COL_TASK_SOURCE:
            task_source = record.get("task_source") or ""
            return "账号组" if task_source == "group" else ("账号" if task_source == "account" else TASK_FIELD_EMPTY_DISPLAY)
        if col == self.COL_ACCOUNT_NAME:
            return task_field_str_or_dash(record.get("platform_username"))
        if col == self.COL_FILE:
            return task_field_str_or_dash(record.get("_file_display") or _file_name_display(record.get("file_path") or ""))
        if col == self.COL_COVER:
            cover_path = record.get("cover_path")
            return "本地封面" if cover_path and os.path.exists(str(cover_path)) else "首帧封面"
        if col == self.COL_TITLE:
            return task_field_str_or_dash(record.get("title"))
        if col == self.COL_DESCRIPTION:
            return task_field_str_or_dash(record.get("description"))
        if col == self.COL_SCHEDULED_TIME:
            return format_schedule_time_st_str(record.get("scheduled_publish_time")) or "立即发布"
        if col == self.COL_ORIGINAL:
            try:
                full = format_work_declaration_table_cell(
                    (record.get("platform") or "").strip(),
                    record.get("privacy_settings"),
                    empty_display=TASK_FIELD_EMPTY_DISPLAY,
                )
            except Exception:
                full = TASK_FIELD_EMPTY_DISPLAY
            return full
        if col == self.COL_MUSIC:
            return format_cart_info_table_cell((record.get("cart_info") or "").strip())
        if col == self.COL_CART:
            return "✓" if (record.get("anchor_info") or "").strip() else TASK_FIELD_EMPTY_DISPLAY
        if col == self.COL_GROUP_BUY:
            return format_poi_table_cell_display(
                record.get("poi_info"),
                platform=(record.get("platform") or "").strip(),
                wechat_empty_location_open_picker=record.get("wechat_empty_location_open_picker"),
            )
        if col == self.COL_LOCATION:
            return _recycle_status_display((record.get("status") or "").strip())
        if col == self.COL_STATUS:
            return task_field_str_or_dash(record.get("_folder_display") or _folder_display(record.get("file_path") or ""))
        if col == self.COL_FILE_LOCATION:
            return _recycle_source_label((record.get("status") or "").strip())
        if col == self.COL_ACTION:
            return self._action_text
        return ""

    def _tooltip_value(self, record: Dict[str, Any], col: int) -> str:
        if col == self.COL_CREATE_TIME:
            if self._recycle_page:
                return _format_timestamp(record.get("created_at"))
            value = (
                (record.get("updated_at") or record.get("created_at"))
                if self._success_page
                else record.get("created_at")
            )
            return _format_timestamp(value)
        if col == self.COL_SCHEDULED_TIME:
            return (
                format_schedule_time_st_str(record.get("scheduled_publish_time"))
                or "立即发布"
            )
        if col == self.COL_COVER:
            cover_path = record.get("cover_path")
            if self._recycle_page:
                if cover_path and os.path.exists(str(cover_path)):
                    return "本地封面"
                return "首帧封面"
            return "本地封面" if cover_path else "首帧封面"
        if col == self.COL_TYPE:
            return "图文" if _record_is_image_task(record) else "视频"
        if col == self.COL_ACCOUNT_NAME:
            return str(record.get("platform_username") or "").strip()
        if col == self.COL_STATUS and not self._recycle_page:
            status = (record.get("status") or "").strip()
            return {
                "success": "✅ 成功",
                "failed": "❌ 失败",
                "pending": "⏳ 待发布",
            }.get(status, status) if status else TASK_FIELD_EMPTY_DISPLAY
        if col == self.COL_TITLE:
            return str(record.get("title") or "")
        if col == self.COL_DESCRIPTION:
            return str(record.get("description") or "")
        if col == self.COL_FILE:
            return str(record.get("file_path") or "")
        if col == self.COL_ORIGINAL:
            try:
                return format_work_declaration_table_cell(
                    (record.get("platform") or "").strip(),
                    record.get("privacy_settings"),
                    empty_display=TASK_FIELD_EMPTY_DISPLAY,
                )
            except Exception:
                return ""
        if self._recycle_page and col == self.COL_STATUS:
            return str(record.get("_folder_display") or _folder_display(record.get("file_path") or ""))
        if not self._recycle_page and col == self.COL_FILE_LOCATION:
            return str(record.get("_folder_display") or _folder_display(record.get("file_path") or ""))
        return ""

    def _rebuild_index(self) -> None:
        self._row_by_id = {}
        for row, record in enumerate(self._records):
            try:
                self._row_by_id[int(record.get("id"))] = row
            except (TypeError, ValueError):
                continue
