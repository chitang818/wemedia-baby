# -*- coding: utf-8 -*-
"""账号组（多平台）：右栏按「原创声明 / 作品申明」功能分区（与左栏对应）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

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

from .constants import (
    H_GAP,
    LABEL_WIDTH,
    RIGHT_DECL_ENABLE_CHECK_LABEL,
    RIGHT_DECL_XHS_ORIG_LABEL,
    RIGHT_SECTION_ORIGINAL_TITLE,
    RIGHT_SECTION_TITLE_STYLE,
    RIGHT_SECTION_WORK_TITLE,
    ROW_GAP,
    RIGHT_WORK_DECL_COMBO_WIDTH,
    SHARED_ROW_MIN_HEIGHT,
)

_ORIGINAL_PLATFORMS = ("wechat_video", "xiaohongshu")
_WORK_PLATFORMS = ("douyin", "kuaishou", "xiaohongshu")

_WORK_ROW_LABELS = {
    "douyin": "抖音申明",
    "kuaishou": "快手申明",
    "xiaohongshu": "小红书",
}
_ORIGINAL_ROW_LABELS = {
    "wechat_video": "视频号",
    "xiaohongshu": "小红书",
}


def original_platform_ids(platform_ids: Set[str]) -> List[str]:
    return [p for p in _ORIGINAL_PLATFORMS if p in platform_ids]


def work_platform_ids(platform_ids: Set[str], *, is_image_mode: bool) -> List[str]:
    out: List[str] = []
    for pid in _WORK_PLATFORMS:
        if pid not in platform_ids:
            continue
        cap = capabilities_for_platform(pid, is_image_mode=is_image_mode)
        if cap.show_work_declaration:
            out.append(pid)
    return out


def platforms_with_declaration(
    platform_ids: Set[str], *, is_image_mode: bool
) -> List[str]:
    """任一分区有控件即视为有内容（供 has_content）。"""
    orig = original_platform_ids(platform_ids)
    work = work_platform_ids(platform_ids, is_image_mode=is_image_mode)
    return orig + [p for p in work if p not in orig]


class GroupPlatformDeclarationPanel(QWidget):
    """混平台账号组：右栏「原创声明」「作品申明」两个功能分区。"""

    def __init__(
        self, parent: Optional[QWidget] = None, *, is_image_mode: bool = False
    ) -> None:
        super().__init__(parent)
        self._is_image_mode = is_image_mode
        self._syncing = False
        self._platform_ids: List[str] = []
        self._original_ids: List[str] = []
        self._work_ids: List[str] = []
        self._blocks: Dict[str, Dict[str, Any]] = {}

        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(ROW_GAP)
        self.hide()

    def has_content(self, platform_ids: Set[str]) -> bool:
        return bool(
            platforms_with_declaration(
                platform_ids, is_image_mode=self._is_image_mode
            )
        )

    def refresh(self, context: str, platform_ids: Set[str]) -> None:
        if context != "mixed":
            self.hide()
            return
        self._original_ids = original_platform_ids(platform_ids)
        self._work_ids = work_platform_ids(
            platform_ids, is_image_mode=self._is_image_mode
        )
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
                    if "attr_auto" in block:
                        block["attr_auto"].blockSignals(True)
                        block["attr_auto"].setChecked(
                            bool(wd.get(KEY_XHS_CONTENT_ATTR_AUTO, False))
                        )
                        block["attr_auto"].blockSignals(False)
                    if "combo" in block:
                        self._set_combo_data(
                            block["combo"], wd.get(KEY_XHS_CONTENT_ATTR)
                        )
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
                    if "attr_auto" in block:
                        block["attr_auto"].blockSignals(True)
                        block["attr_auto"].setChecked(
                            declaration_auto_apply(ps, KEY_XHS_CONTENT_ATTR_AUTO)
                        )
                        block["attr_auto"].blockSignals(False)
                    if "combo" in block:
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
                if "combo" in block:
                    raw = self._combo_data(block["combo"])
                    out[KEY_XHS_CONTENT_ATTR] = normalize_xhs_content_attr(
                        str(raw or "") or None
                    )
                if "attr_auto" in block:
                    out[KEY_XHS_CONTENT_ATTR_AUTO] = bool(block["attr_auto"].isChecked())
            elif pid == "wechat_video":
                out[KEY_IS_ORIGINAL] = bool(block["orig"].isChecked())
        return out

    def reset_to_defaults(self) -> None:
        save_persisted_single_declare_original(False)
        self.sync_from_storage()

    @staticmethod
    def _finalize_row(row_w: QWidget) -> QWidget:
        row_w.setMinimumHeight(SHARED_ROW_MIN_HEIGHT)
        lay = row_w.layout()
        if isinstance(lay, QHBoxLayout):
            lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        return row_w

    @staticmethod
    def _row_label(text: str, parent: QWidget, *, tooltip: str = "") -> BodyLabel:
        label = BodyLabel(text, parent)
        label.setFixedWidth(LABEL_WIDTH)
        if tooltip:
            apply_instructional_tooltip(
                tooltip, label, position=ToolTipPosition.BOTTOM
            )
        return label

    @staticmethod
    def _section_title_row(title: str, parent: QWidget) -> QWidget:
        row_w = QWidget(parent)
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(H_GAP)
        lb = BodyLabel(title, row_w)
        lb.setFixedWidth(LABEL_WIDTH)
        lb.setStyleSheet(RIGHT_SECTION_TITLE_STYLE)
        row.addWidget(lb)
        row.addStretch(1)
        return GroupPlatformDeclarationPanel._finalize_row(row_w)

    @staticmethod
    def _configure_work_decl_combo(combo: ComboBox) -> None:
        combo.setFixedWidth(RIGHT_WORK_DECL_COMBO_WIDTH)
        combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _build_original_platform_row(
        self, pid: str, parent: QWidget, layout: QVBoxLayout
    ) -> Dict[str, Any]:
        block: Dict[str, Any] = {"platform": pid}
        row_label = _ORIGINAL_ROW_LABELS.get(pid) or get_platform_display_name(pid)
        tip = f"{get_platform_display_name(pid)} · 原创声明"

        row_w = QWidget(parent)
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(H_GAP)
        row.addWidget(self._row_label(row_label, row_w, tooltip=tip))
        block["orig"] = CheckBox(RIGHT_DECL_XHS_ORIG_LABEL, row_w)
        if pid == "xiaohongshu":
            apply_instructional_tooltip(
                "与「内容属性」无关，可分别设置",
                block["orig"],
                position=ToolTipPosition.BOTTOM,
            )
            block["orig"].stateChanged.connect(
                lambda _s, p=pid: self._persist_platform(p)
            )
        else:
            apply_instructional_tooltip(
                "仅对视频号发布任务生效",
                block["orig"],
                position=ToolTipPosition.BOTTOM,
            )
            block["orig"].stateChanged.connect(self._on_wechat_original_changed)
        row.addWidget(block["orig"])
        row.addStretch(1)
        layout.addWidget(self._finalize_row(row_w))
        return block

    def _build_work_auto_combo_row(
        self, pid: str, parent: QWidget, layout: QVBoxLayout
    ) -> Dict[str, Any]:
        block: Dict[str, Any] = {"platform": pid}
        row_label = _WORK_ROW_LABELS.get(pid) or get_platform_display_name(pid)
        tip = f"{get_platform_display_name(pid)} · 作品申明"

        row_w = QWidget(parent)
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(H_GAP)
        row.addWidget(self._row_label(row_label, row_w, tooltip=tip))
        block["auto"] = CheckBox(RIGHT_DECL_ENABLE_CHECK_LABEL, row_w)
        apply_instructional_tooltip(
            "发布时自动按右侧选项勾选作品申明",
            block["auto"],
            position=ToolTipPosition.BOTTOM,
        )
        block["combo"] = ComboBox(row_w)
        choices = DOUYIN_CHOICES if pid == "douyin" else KUAISHOU_CHOICES
        for val, text in choices:
            block["combo"].addItem(text, userData=val)
        self._configure_work_decl_combo(block["combo"])
        block["auto"].toggled.connect(lambda _c, p=pid: self._on_auto_toggled(p))
        block["combo"].currentIndexChanged.connect(
            lambda _i, p=pid: self._persist_platform(p)
        )
        row.addWidget(block["auto"])
        row.addWidget(block["combo"], 0)
        row.addStretch(1)
        layout.addWidget(self._finalize_row(row_w))
        return block

    def _build_xhs_work_row(
        self, parent: QWidget, layout: QVBoxLayout, block: Dict[str, Any]
    ) -> None:
        """小红书作品申明：与抖音/快手同款单行（启用 + 内容属性下拉）。"""
        tip = f"{get_platform_display_name('xiaohongshu')} · 作品申明"

        row_w = QWidget(parent)
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(H_GAP)
        row.addWidget(
            self._row_label(_WORK_ROW_LABELS["xiaohongshu"], row_w, tooltip=tip)
        )
        block["attr_auto"] = CheckBox(RIGHT_DECL_ENABLE_CHECK_LABEL, row_w)
        apply_instructional_tooltip(
            "发布时自动按右侧选项设置内容属性",
            block["attr_auto"],
            position=ToolTipPosition.BOTTOM,
        )
        block["attr_auto"].toggled.connect(
            lambda _c, p="xiaohongshu": self._on_auto_toggled(p)
        )
        block["combo"] = ComboBox(row_w)
        for val, text in XHS_CONTENT_ATTR_CHOICES:
            block["combo"].addItem(text, userData=val)
        self._configure_work_decl_combo(block["combo"])
        block["combo"].currentIndexChanged.connect(
            lambda _i, p="xiaohongshu": self._persist_platform(p)
        )
        row.addWidget(block["attr_auto"])
        row.addWidget(block["combo"], 0)
        row.addStretch(1)
        layout.addWidget(self._finalize_row(row_w))

    def _rebuild_blocks(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._blocks.clear()

        if self._original_ids:
            section_o = QWidget(self)
            lo = QVBoxLayout(section_o)
            lo.setContentsMargins(0, 0, 0, 0)
            lo.setSpacing(ROW_GAP)
            lo.addWidget(self._section_title_row(RIGHT_SECTION_ORIGINAL_TITLE, section_o))
            for pid in self._original_ids:
                self._blocks[pid] = self._build_original_platform_row(pid, section_o, lo)
            self._layout.addWidget(section_o)

        if self._work_ids:
            section_w = QWidget(self)
            lw = QVBoxLayout(section_w)
            lw.setContentsMargins(0, 0, 0, 0)
            lw.setSpacing(ROW_GAP)
            lw.addWidget(self._section_title_row(RIGHT_SECTION_WORK_TITLE, section_w))
            for pid in self._work_ids:
                if pid in ("douyin", "kuaishou"):
                    self._blocks[pid] = self._build_work_auto_combo_row(
                        pid, section_w, lw
                    )
                elif pid == "xiaohongshu":
                    block = self._blocks.get("xiaohongshu")
                    if block is None:
                        block = {"platform": "xiaohongshu"}
                    self._build_xhs_work_row(section_w, lw, block)
                    self._blocks["xiaohongshu"] = block
            self._layout.addWidget(section_w)

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
            if "combo" in block:
                raw = self._combo_data(block["combo"])
                cur[KEY_XHS_CONTENT_ATTR] = normalize_xhs_content_attr(str(raw or "") or None)
            if "attr_auto" in block:
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
        elif platform_id == "xiaohongshu" and "combo" in block and "attr_auto" in block:
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
