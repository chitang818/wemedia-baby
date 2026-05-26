# -*- coding: utf-8 -*-
"""
位置推广选择控件
ComboBox 展示位置简称；右侧显示当前平台搜索词。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout

from qfluentwidgets import ComboBox, BodyLabel

from src.domain.publish.location_settings import (
    LOCATION_PLATFORM_FIELD_MAP,
    format_poi_info_from_short_name,
    parse_location_short_name_from_storage,
)
from src.domain.publish.location_settings.constants import LOCATION_MODE_CHOICES_SET
from src.infrastructure.common.async_task_registry import get_async_task_registry

logger = logging.getLogger(__name__)

_PLACEHOLDER = "（未选择）"


class LocationSelectorWidget(QWidget):
    """位置推广选择行：[位置简称 ComboBox] [平台搜索词只读标签]"""

    selection_changed = Signal()

    def __init__(
        self, parent: Optional[QWidget] = None, *, initial_short_name: str = ""
    ) -> None:
        super().__init__(parent)

        self._platform: str = ""
        self._items: List[Dict[str, Any]] = []
        self._initial_short_name = (initial_short_name or "").strip()
        self._load_task: Optional[asyncio.Task] = None
        self._load_retry_count = 0
        self._closed = False
        self._load_retry_timer = QTimer(self)
        self._load_retry_timer.setSingleShot(True)
        self._load_retry_timer.timeout.connect(self._schedule_load_locations)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._combo = ComboBox(self)
        self._combo.setMinimumWidth(160)
        self._combo.addItem(_PLACEHOLDER)
        self._combo.currentIndexChanged.connect(self._on_selection_changed)
        layout.addWidget(self._combo)

        self._value_label = BodyLabel("", self)
        self._value_label.setWordWrap(False)
        self._value_label.setMinimumWidth(120)
        self._value_label.setMaximumWidth(400)
        self._value_label.setStyleSheet("color: #888; font-size: 12px;")
        self._value_label.setToolTip("当前平台对应的地理位置搜索词")
        layout.addWidget(self._value_label)
        layout.addStretch()

        self._load_retry_timer.start(0)

    def _schedule_load_locations(self) -> None:
        if self._closed:
            return
        if self._load_task is not None and not self._load_task.done():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._load_retry_count += 1
            if self._load_retry_count <= 20:
                self._load_retry_timer.start(50)
            else:
                logger.warning("跳过位置库加载：qasync 事件循环未启动")
            return

        self._load_task = get_async_task_registry().create_task(
            self._load_locations(),
            name="ui.location_selector.load_locations",
            group="ui",
        )

    def get_selected_short_name(self) -> str:
        text = self._combo.currentText()
        return "" if text == _PLACEHOLDER else text

    def build_poi_info_storage(self, location_mode: str = "") -> str:
        """当前选中位置写入 poi_info 存储串；未选返回空串。"""
        sn = self.get_selected_short_name()
        if not sn:
            return ""
        mode = (location_mode or "").strip()
        if mode not in LOCATION_MODE_CHOICES_SET:
            mode = ""
        return format_poi_info_from_short_name(sn, mode)

    @staticmethod
    def short_name_from_poi_info(poi_info_raw: str) -> str:
        return parse_location_short_name_from_storage(poi_info_raw or "")

    def set_combo_fixed_width(self, width: int) -> None:
        """固定位置简称下拉宽度（如「更多发布设置」左栏与其它下拉对齐）。"""
        w = max(1, int(width))
        self._combo.setFixedWidth(w)

    def set_platform(self, platform: str) -> None:
        self._platform = (platform or "").strip()
        self._refresh_value_label()

    def closeEvent(self, event) -> None:
        self._closed = True
        self._load_retry_timer.stop()
        if getattr(self, "_load_task", None) is not None and not self._load_task.done():
            self._load_task.cancel()
        super().closeEvent(event)

    def apply_record(self, short_name: str) -> None:
        if not short_name:
            self._combo.setCurrentIndex(0)
            return
        idx = self._combo.findText(short_name)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        else:
            logger.warning("编辑回填：位置简称「%s」不在当前位置库，已设为未选择", short_name)
            self._combo.setCurrentIndex(0)

    async def _load_locations(self) -> None:
        try:
            from src.infrastructure.storage.repositories.location_promotion_repository import (
                LocationPromotionRepository,
            )

            rows = await LocationPromotionRepository.list_all()
            self._items = rows

            current_text = self._combo.currentText()
            self._combo.blockSignals(True)
            while self._combo.count() > 0:
                self._combo.removeItem(0)
            self._combo.addItem(_PLACEHOLDER)
            for row in rows:
                name = row.get("short_name") or ""
                if name:
                    self._combo.addItem(name)

            if current_text and current_text != _PLACEHOLDER:
                idx = self._combo.findText(current_text)
                if idx >= 0:
                    self._combo.setCurrentIndex(idx)
            self._combo.blockSignals(False)
            self._refresh_value_label()
            if self._initial_short_name:
                self.apply_record(self._initial_short_name)
        except Exception as e:
            logger.error("加载位置推广列表失败: %s", e, exc_info=True)

    def _on_selection_changed(self, _index: int) -> None:
        self._refresh_value_label()
        self.selection_changed.emit()

    def _refresh_value_label(self) -> None:
        short_name = self.get_selected_short_name()
        if not short_name or not self._items:
            self._value_label.setText("")
            return

        db_field = LOCATION_PLATFORM_FIELD_MAP.get(self._platform, "")
        if not db_field:
            self._value_label.setText("")
            return

        matched = next((r for r in self._items if r.get("short_name") == short_name), None)
        if matched is None:
            self._value_label.setText("")
            return

        val = (matched.get(db_field) or "").strip()
        display = val if len(val) <= 60 else val[:57] + "..."
        self._value_label.setText(display)
        self._value_label.setToolTip(val or "（该平台暂无配置）")
