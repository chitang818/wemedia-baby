# -*- coding: utf-8 -*-
"""账号组（多平台）：右栏按平台展示作品申明 / 原创声明。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import BodyLabel, CheckBox, ComboBox

from src.domain.publish.single_publish_options_capabilities import (
    capabilities_for_platform,
)
from src.domain.publish.work_declaration import (
    DOUYIN_CHOICES,
    KEY_DOUYIN,
    KEY_DOUYIN_AUTO,
    KEY_IS_ORIGINAL,
    KEY_KUAISHOU,
    KEY_KUAISHOU_AUTO,
    KEY_XHS_CONTENT_ATTR,
    KEY_XHS_CONTENT_ATTR_AUTO,
    KEY_XHS_ORIGINAL,
    KUAISHOU_CHOICES,
    XHS_CONTENT_ATTR_CHOICES,
    declaration_auto_apply,
    normalize_douyin_value,
    normalize_kuaishou_value,
    normalize_xhs_content_attr,
)
from src.ui.publish.work_description.single_declare_original_prefs import (
    load_persisted_single_declare_original,
    save_persisted_single_declare_original,
)
from src.ui.publish.work_description.work_declaration_prefs import (
    load_persisted_work_declaration,
    save_persisted_work_declaration,
)
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip
from src.utils.platform_names import get_platform_display_name

from .constants import COMBO_WIDTH, H_GAP, ROW_GAP

# 右栏多平台申明块展示顺序
_DECL_PLATFORM_ORDER = ("douyin", "kuaishou", "xiaohongshu", "wechat_video")


def platforms_with_declaration(
    platform_ids: Set[str], *, is_image_mode: bool
) -> List[str]:
    """账号组内需要展示申明控件的平台 id 列表（有序）。"""
    out: List[str] = []
    for pid in _DECL_PLATFORM_ORDER:
        if pid not in platform_ids:
            continue
        if pid == "wechat_video":
            out.append(pid)
            continue
        cap = capabilities_for_platform(pid, is_image_mode=is_image_mode)
        if cap.show_work_declaration:
            out.append(pid)
    return out


class GroupPlatformDeclarationPanel(QWidget):
    """混平台账号组：每个平台一块，置于右栏抖音位置设置下方。"""

    def __init__(
        self, parent: Optional[QWidget] = None, *, is_image_mode: bool = False
    ) -> None:
        super().__init__(parent)
        self._is_image_mode = is_image_mode
        self._syncing = False
        self._platform_ids: List[str] = []
        self._blocks: Dict[str, Dict[str, Any]] = {}

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(ROW_GAP)
        self.hide()

    def has_content(self, platform_ids: Set[str]) -> bool:
        return bool(platforms_with_declaration(platform_ids, is_image_mode=self._is_image_mode))

    def refresh(self, context: str, platform_ids: Set[str]) -> None:
        if context != "mixed":
            self.hide()
            return
        self._platform_ids = platforms_with_declaration(
            platform_ids, is_image_mode=self._is_image_mode
        )
        if not self._platform_ids:
            self.hide()
            return
        self.show()
        self._rebuild_blocks()
        self.sync_from_storage()

    def sync_from_storage(self) -> None:
        if not self._platform_ids:
            return
        self._syncing = True
        try:
            wd = load_persisted_work_declaration()
            for pid in self._platform_ids:
                block = self._blocks.get(pid)
                if not block:
                    continue
                if pid == "douyin":
                    self._set_combo_data(block["combo"], wd.get(KEY_DOUYIN))
                    block["auto"].blockSignals(True)
                    block["auto"].setChecked(bool(wd.get(KEY_DOUYIN_AUTO, False)))
                    block["auto"].blockSignals(False)
                elif pid == "kuaishou":
                    self._set_combo_data(block["combo"], wd.get(KEY_KUAISHOU))
                    block["auto"].blockSignals(True)
                    block["auto"].setChecked(bool(wd.get(KEY_KUAISHOU_AUTO, False)))
                    block["auto"].blockSignals(False)
                elif pid == "xiaohongshu":
                    block["orig"].blockSignals(True)
                    block["orig"].setChecked(bool(wd.get(KEY_XHS_ORIGINAL, False)))
                    block["orig"].blockSignals(False)
                    block["attr_auto"].blockSignals(True)
                    block["attr_auto"].setChecked(
                        bool(wd.get(KEY_XHS_CONTENT_ATTR_AUTO, False))
                    )
                    block["attr_auto"].blockSignals(False)
                    self._set_combo_data(block["combo"], wd.get(KEY_XHS_CONTENT_ATTR))
                elif pid == "wechat_video":
                    block["orig"].blockSignals(True)
                    block["orig"].setChecked(load_persisted_single_declare_original())
                    block["orig"].blockSignals(False)
            self._update_all_auto_combos()
        finally:
            self._syncing = False

    def apply_privacy_dict(self, ps: Dict[str, Any]) -> None:
        if not self._platform_ids:
            return
        self._syncing = True
        try:
            for pid in self._platform_ids:
                block = self._blocks.get(pid)
                if not block:
                    continue
                if pid == "douyin":
                    self._set_combo_data(
                        block["combo"],
                        normalize_douyin_value(str(ps.get(KEY_DOUYIN) or "") or None),
                    )
                    block["auto"].blockSignals(True)
                    block["auto"].setChecked(declaration_auto_apply(ps, KEY_DOUYIN_AUTO))
                    block["auto"].blockSignals(False)
                elif pid == "kuaishou":
                    self._set_combo_data(
                        block["combo"],
                        normalize_kuaishou_value(str(ps.get(KEY_KUAISHOU) or "") or None),
                    )
                    block["auto"].blockSignals(True)
                    block["auto"].setChecked(
                        declaration_auto_apply(ps, KEY_KUAISHOU_AUTO)
                    )
                    block["auto"].blockSignals(False)
                elif pid == "xiaohongshu":
                    block["orig"].blockSignals(True)
                    block["orig"].setChecked(bool(ps.get(KEY_XHS_ORIGINAL, False)))
                    block["orig"].blockSignals(False)
                    block["attr_auto"].blockSignals(True)
                    block["attr_auto"].setChecked(
                        declaration_auto_apply(ps, KEY_XHS_CONTENT_ATTR_AUTO)
                    )
                    block["attr_auto"].blockSignals(False)
                    self._set_combo_data(
                        block["combo"],
                        normalize_xhs_content_attr(
                            str(ps.get(KEY_XHS_CONTENT_ATTR) or "") or None
                        ),
                    )
                elif pid == "wechat_video":
                    block["orig"].blockSignals(True)
                    block["orig"].setChecked(bool(ps.get(KEY_IS_ORIGINAL, False)))
                    block["orig"].blockSignals(False)
            self._update_all_auto_combos()
        finally:
            self._syncing = False

    def collect_declaration_privacy(self) -> Dict[str, Any]:
        wd = load_persisted_work_declaration()
        out: Dict[str, Any] = dict(wd)
        for pid in self._platform_ids:
            block = self._blocks.get(pid)
            if not block:
                continue
            if pid == "douyin":
                raw = self._combo_data(block["combo"])
                out[KEY_DOUYIN] = normalize_douyin_value(str(raw or "") or None)
                out[KEY_DOUYIN_AUTO] = bool(block["auto"].isChecked())
            elif pid == "kuaishou":
                raw = self._combo_data(block["combo"])
                out[KEY_KUAISHOU] = normalize_kuaishou_value(str(raw or "") or None)
                out[KEY_KUAISHOU_AUTO] = bool(block["auto"].isChecked())
            elif pid == "xiaohongshu":
                out[KEY_XHS_ORIGINAL] = bool(block["orig"].isChecked())
                raw = self._combo_data(block["combo"])
                out[KEY_XHS_CONTENT_ATTR] = normalize_xhs_content_attr(str(raw or "") or None)
                out[KEY_XHS_CONTENT_ATTR_AUTO] = bool(block["attr_auto"].isChecked())
            elif pid == "wechat_video":
                out[KEY_IS_ORIGINAL] = bool(block["orig"].isChecked())
        return out

    def reset_to_defaults(self) -> None:
        save_persisted_single_declare_original(False)
        self.sync_from_storage()

    def _rebuild_blocks(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._blocks.clear()

        for pid in self._platform_ids:
            wrap = QWidget(self)
            v = QVBoxLayout(wrap)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(H_GAP)

            title = BodyLabel(f"{get_platform_display_name(pid)} · 作品申明", wrap)
            title.setStyleSheet("color: #333; font-weight: 600; font-size: 13px;")
            v.addWidget(title)

            controls = QWidget(wrap)
            row = QHBoxLayout(controls)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(H_GAP)

            block: Dict[str, Any] = {"platform": pid}
            if pid == "douyin":
                block["auto"] = CheckBox("发布时自动勾选", controls)
                block["combo"] = ComboBox(controls)
                for val, text in DOUYIN_CHOICES:
                    block["combo"].addItem(text, userData=val)
                block["combo"].setFixedWidth(COMBO_WIDTH)
                block["auto"].toggled.connect(
                    lambda _c, p=pid: self._on_auto_toggled(p)
                )
                block["combo"].currentIndexChanged.connect(
                    lambda _i, p=pid: self._persist_platform(p)
                )
                row.addWidget(block["auto"])
                row.addWidget(block["combo"])
            elif pid == "kuaishou":
                block["auto"] = CheckBox("发布时自动勾选", controls)
                block["combo"] = ComboBox(controls)
                for val, text in KUAISHOU_CHOICES:
                    block["combo"].addItem(text, userData=val)
                block["combo"].setFixedWidth(COMBO_WIDTH)
                block["auto"].toggled.connect(
                    lambda _c, p=pid: self._on_auto_toggled(p)
                )
                block["combo"].currentIndexChanged.connect(
                    lambda _i, p=pid: self._persist_platform(p)
                )
                row.addWidget(block["auto"])
                row.addWidget(block["combo"])
            elif pid == "xiaohongshu":
                block["orig"] = CheckBox("申明原创", controls)
                apply_instructional_tooltip(
                    "与「内容属性」无关，可分别设置",
                    block["orig"],
                    position=ToolTipPosition.BOTTOM,
                )
                block["attr_auto"] = CheckBox("属性自动勾选", controls)
                block["combo"] = ComboBox(controls)
                for val, text in XHS_CONTENT_ATTR_CHOICES:
                    block["combo"].addItem(text, userData=val)
                block["combo"].setFixedWidth(COMBO_WIDTH)
                block["orig"].stateChanged.connect(
                    lambda _s, p=pid: self._persist_platform(p)
                )
                block["attr_auto"].toggled.connect(
                    lambda _c, p=pid: self._on_auto_toggled(p)
                )
                block["combo"].currentIndexChanged.connect(
                    lambda _i, p=pid: self._persist_platform(p)
                )
                row.addWidget(block["orig"])
                row.addWidget(block["attr_auto"])
                row.addWidget(block["combo"])
            elif pid == "wechat_video":
                block["orig"] = CheckBox("申明原创", controls)
                apply_instructional_tooltip(
                    "仅对视频号发布任务生效",
                    block["orig"],
                    position=ToolTipPosition.BOTTOM,
                )
                block["orig"].stateChanged.connect(self._on_wechat_original_changed)
                row.addWidget(block["orig"])

            row.addStretch(1)
            v.addWidget(controls)
            self._layout.addWidget(wrap)
            self._blocks[pid] = block

    def _on_auto_toggled(self, platform_id: str) -> None:
        self._update_auto_combo(platform_id)
        self._persist_platform(platform_id)

    def _on_wechat_original_changed(self) -> None:
        if self._syncing:
            return
        block = self._blocks.get("wechat_video")
        if not block:
            return
        save_persisted_single_declare_original(bool(block["orig"].isChecked()))

    def _persist_platform(self, platform_id: str) -> None:
        if self._syncing:
            return
        block = self._blocks.get(platform_id)
        if not block:
            return
        cur = load_persisted_work_declaration()
        if platform_id == "douyin":
            raw = self._combo_data(block["combo"])
            cur[KEY_DOUYIN] = normalize_douyin_value(str(raw or "") or None)
            cur[KEY_DOUYIN_AUTO] = bool(block["auto"].isChecked())
        elif platform_id == "kuaishou":
            raw = self._combo_data(block["combo"])
            cur[KEY_KUAISHOU] = normalize_kuaishou_value(str(raw or "") or None)
            cur[KEY_KUAISHOU_AUTO] = bool(block["auto"].isChecked())
        elif platform_id == "xiaohongshu":
            cur[KEY_XHS_ORIGINAL] = bool(block["orig"].isChecked())
            raw = self._combo_data(block["combo"])
            cur[KEY_XHS_CONTENT_ATTR] = normalize_xhs_content_attr(str(raw or "") or None)
            cur[KEY_XHS_CONTENT_ATTR_AUTO] = bool(block["attr_auto"].isChecked())
        save_persisted_work_declaration(cur)

    def _update_all_auto_combos(self) -> None:
        for pid in self._platform_ids:
            self._update_auto_combo(pid)

    def _update_auto_combo(self, platform_id: str) -> None:
        block = self._blocks.get(platform_id)
        if not block:
            return
        if platform_id in ("douyin", "kuaishou") and "combo" in block:
            block["combo"].setEnabled(block["auto"].isChecked())
        elif platform_id == "xiaohongshu" and "combo" in block:
            block["combo"].setEnabled(block["attr_auto"].isChecked())

    @staticmethod
    def _combo_data(combo: ComboBox) -> Any:
        raw = combo.currentData()
        if raw is None and combo.currentIndex() >= 0:
            raw = combo.itemData(combo.currentIndex())
        return raw

    @staticmethod
    def _set_combo_data(combo: ComboBox, value: Any) -> None:
        combo.blockSignals(True)
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                break
        combo.blockSignals(False)
