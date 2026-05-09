# -*- coding: utf-8 -*-
"""
购物车推广商品选择控件
文件路径：src/ui/publish/promotion/cart_selector_widget.py

功能：
  - ComboBox 展示已配置的商品简称列表。
  - 右侧只读标签显示当前选中商品在当前平台的对应值（链接或商品名称）。
  - 提供 get_selected_short_name() / set_platform() / apply_record() 接口供父页面调用。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout

from qfluentwidgets import ComboBox, BodyLabel

from src.domain.publish.promotion_limits import CART_SHORT_TITLE_MAX_LEN
from src.domain.publish.promotion_settings import PLATFORM_FIELD_MAP

logger = logging.getLogger(__name__)

# 未选择商品时的占位项
_PLACEHOLDER = "（未选择）"


class CartSelectorWidget(QWidget):
    """购物车推广商品选择行控件。

    布局：[商品简称 ComboBox]  [平台值只读标签]
    """

    def __init__(
        self, parent: Optional[QWidget] = None, *, initial_short_name: str = ""
    ) -> None:
        super().__init__(parent)

        self._platform: str = ""
        self._items: List[Dict[str, Any]] = []
        self._initial_short_name = (initial_short_name or "").strip()

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
        self._value_label.setToolTip("当前平台对应的商品链接或名称")
        layout.addWidget(self._value_label)
        layout.addStretch()

        asyncio.ensure_future(self._load_products())

    # ---------- 公开接口 ----------

    def get_selected_short_name(self) -> str:
        """返回当前选中的商品简称；未选择时返回空字符串。"""
        text = self._combo.currentText()
        return "" if text == _PLACEHOLDER else text

    def build_cart_info_dict(self) -> Optional[Dict[str, str]]:
        """当前选中商品写入 ``cart_info`` 的 JSON 对象（未选时返回 None）。

        ``cart_short_title`` 为商品短标题（与作品简介无关）；库中未填时用简称占位。
        发布仍只按 ``cart_short_name`` 查各平台链接。
        """
        sn = self.get_selected_short_name()
        if not sn:
            return None
        matched = next((r for r in self._items if r.get("short_name") == sn), None)
        st = (
            (matched.get("short_title") or "").strip()[:CART_SHORT_TITLE_MAX_LEN]
            if matched
            else ""
        )
        disp = st if st else sn
        return {
            "cart_short_name": sn,
            "cart_short_title": disp,
        }

    def set_platform(self, platform: str) -> None:
        """切换当前平台，刷新右侧显示的平台对应值。"""
        self._platform = (platform or "").strip()
        self._refresh_value_label()

    def apply_record(self, short_name: str) -> None:
        """从发布记录回填选中的商品简称（编辑模式）。

        Args:
            short_name: 商品简称字符串。若不在商品库中则保持占位项选中。
        """
        if not short_name:
            self._combo.setCurrentIndex(0)
            return
        idx = self._combo.findText(short_name)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        else:
            # 商品已从库中删除，仍显示简称以便用户感知
            logger.warning("编辑回填：商品简称「%s」不在当前商品库，已设为未选择", short_name)
            self._combo.setCurrentIndex(0)

    # ---------- 内部方法 ----------

    async def _load_products(self) -> None:
        """异步从商品库加载全部商品，填充下拉列表。"""
        try:
            from src.infrastructure.storage.repositories.cart_promotion_repository import (
                CartPromotionRepository,
            )

            rows = await CartPromotionRepository.list_all()
            self._items = rows

            current_text = self._combo.currentText()
            self._combo.blockSignals(True)
            # 保留占位项，重建列表
            while self._combo.count() > 0:
                self._combo.removeItem(0)
            self._combo.addItem(_PLACEHOLDER)
            for row in rows:
                name = row.get("short_name") or ""
                if name:
                    self._combo.addItem(name)

            # 尝试恢复之前的选中（若编辑模式下已 apply_record）
            if current_text and current_text != _PLACEHOLDER:
                idx = self._combo.findText(current_text)
                if idx >= 0:
                    self._combo.setCurrentIndex(idx)
            self._combo.blockSignals(False)
            self._refresh_value_label()
            if self._initial_short_name:
                self.apply_record(self._initial_short_name)
        except Exception as e:
            logger.error("加载购物车商品列表失败: %s", e, exc_info=True)

    def _on_selection_changed(self, _index: int) -> None:
        self._refresh_value_label()

    def _refresh_value_label(self) -> None:
        """根据当前选中商品和平台，刷新右侧只读标签。"""
        short_name = self.get_selected_short_name()
        if not short_name or not self._items:
            self._value_label.setText("")
            return

        db_field = PLATFORM_FIELD_MAP.get(self._platform, "")
        if not db_field:
            self._value_label.setText("")
            return

        matched = next((r for r in self._items if r.get("short_name") == short_name), None)
        if matched is None:
            self._value_label.setText("")
            return

        val = (matched.get(db_field) or "").strip()
        # 截断过长内容，避免撑破布局
        display = val if len(val) <= 60 else val[:57] + "..."
        self._value_label.setText(display)
        self._value_label.setToolTip(val or "（该平台暂无配置）")
