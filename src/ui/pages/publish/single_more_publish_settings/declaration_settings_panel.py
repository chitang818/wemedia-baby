# -*- coding: utf-8 -*-
"""更多发布设置：原创声明（复选框）+ 作品申明（按平台堆叠控件）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import BodyLabel, CheckBox, ComboBox

from src.domain.publish.single_publish_options_capabilities import (
    PublishOptionsCapabilities,
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

from .constants import (
    COMBO_WIDTH,
    H_GAP,
    LABEL_WIDTH,
    MIXED_GROUP_WD_LEFT_HINT,
    ORIGINAL_LEFT_HINT_NOT_APPLICABLE,
    ROW_GAP,
    SHARED_ROW_MIN_HEIGHT,
    WD_LEFT_HINT_NOT_APPLICABLE,
    WD_LEFT_HINT_SELECT_TARGET,
    WD_LEFT_HINT_WECHAT_USE_ORIGINAL,
)

AccountContext = str

_ORIG_PAGE_PROMPT = 0
_ORIG_PAGE_MIXED = 1
_ORIG_PAGE_CHECKBOX = 2
_ORIG_PAGE_NOT_APPLICABLE = 3

_WD_PAGE_PROMPT = 0
_WD_PAGE_MIXED = 1
_WD_PAGE_WECHAT = 2
_WD_PAGE_DOUYIN = 3
_WD_PAGE_KUAISHOU = 4
_WD_PAGE_XIAOHONGSHU = 5


class DeclarationSettingsPanel(QWidget):
    """左栏：原创声明行 + 作品申明行。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._context: AccountContext = "none"
        self._syncing = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(ROW_GAP)

        self._row_original = self._finalize_row(self._build_original_row())
        root.addWidget(self._row_original)
        self._row_work_declaration = self._finalize_row(self._build_work_declaration_row())
        root.addWidget(self._row_work_declaration)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

    @staticmethod
    def _finalize_row(row_w: QWidget) -> QWidget:
        row_w.setMinimumHeight(SHARED_ROW_MIN_HEIGHT)
        lay = row_w.layout()
        if isinstance(lay, QHBoxLayout):
            lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        return row_w

    def _build_original_row(self) -> QWidget:
        row_w = QWidget(self)
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(H_GAP)
        label = BodyLabel("原创声明", row_w)
        label.setFixedWidth(LABEL_WIDTH)

        self._orig_stack = QStackedWidget(row_w)
        self._orig_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._orig_stack.setFixedHeight(SHARED_ROW_MIN_HEIGHT)

        def _hint_page(parent: QWidget, text: str) -> QWidget:
            w = QWidget(parent)
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            lb = BodyLabel(text, w)
            lb.setStyleSheet("color: #888;")
            h.addWidget(lb)
            h.addStretch(1)
            return w

        self._orig_stack.addWidget(
            _hint_page(row_w, WD_LEFT_HINT_SELECT_TARGET)
        )
        self._orig_stack.addWidget(_hint_page(row_w, MIXED_GROUP_WD_LEFT_HINT))
        p_chk = QWidget(row_w)
        p_chk_l = QHBoxLayout(p_chk)
        p_chk_l.setContentsMargins(0, 0, 0, 0)
        self._original_check = CheckBox("申明原创", p_chk)
        apply_instructional_tooltip(
            "视频号：声明原创；小红书：原创声明开关（与作品申明内容属性无关）",
            self._original_check,
            position=ToolTipPosition.BOTTOM,
        )
        self._original_check.stateChanged.connect(self._on_original_changed)
        p_chk_l.addWidget(self._original_check)
        p_chk_l.addStretch(1)
        self._orig_stack.addWidget(p_chk)
        self._orig_stack.addWidget(
            _hint_page(row_w, ORIGINAL_LEFT_HINT_NOT_APPLICABLE)
        )

        row.addWidget(label)
        row.addWidget(self._orig_stack, 1)
        return row_w

    def _build_work_declaration_row(self) -> QWidget:
        row_w = QWidget(self)
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(H_GAP)
        label = BodyLabel("作品申明", row_w)
        label.setFixedWidth(LABEL_WIDTH)

        self._wd_stack = QStackedWidget(row_w)
        self._wd_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._wd_stack.setFixedHeight(SHARED_ROW_MIN_HEIGHT)

        def _page_hbox(parent: QWidget) -> tuple[QWidget, QHBoxLayout]:
            w = QWidget(parent)
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(H_GAP)
            return w, h

        p0, p0l = _page_hbox(row_w)
        self._wd_prompt_label = BodyLabel(WD_LEFT_HINT_SELECT_TARGET, p0)
        self._wd_prompt_label.setStyleSheet("color: #888;")
        p0l.addWidget(self._wd_prompt_label)
        p0l.addStretch(1)
        self._wd_stack.addWidget(p0)

        p1, p1l = _page_hbox(row_w)
        self._wd_mixed_hint_label = BodyLabel(MIXED_GROUP_WD_LEFT_HINT, p1)
        self._wd_mixed_hint_label.setStyleSheet("color: #888;")
        p1l.addWidget(self._wd_mixed_hint_label)
        p1l.addStretch(1)
        self._wd_stack.addWidget(p1)

        p2, p2l = _page_hbox(row_w)
        self._wd_wechat_hint_label = BodyLabel(WD_LEFT_HINT_WECHAT_USE_ORIGINAL, p2)
        self._wd_wechat_hint_label.setStyleSheet("color: #888;")
        p2l.addWidget(self._wd_wechat_hint_label)
        p2l.addStretch(1)
        self._wd_stack.addWidget(p2)

        p3, p3l = _page_hbox(row_w)
        self._wd_dy_auto = CheckBox("发布时自动勾选", p3)
        apply_instructional_tooltip(
            "勾选后发布时自动在网页上选中对应申明",
            self._wd_dy_auto,
            position=ToolTipPosition.BOTTOM,
        )
        self._wd_dy_combo = ComboBox(p3)
        apply_instructional_tooltip(
            "与抖音发布页「作品申明」选项一致",
            self._wd_dy_combo,
            position=ToolTipPosition.BOTTOM,
        )
        for val, text in DOUYIN_CHOICES:
            self._wd_dy_combo.addItem(text, userData=val)
        self._wd_dy_combo.setFixedWidth(COMBO_WIDTH)
        p3l.addWidget(self._wd_dy_auto)
        p3l.addWidget(self._wd_dy_combo)
        p3l.addStretch(1)
        self._wd_stack.addWidget(p3)

        p4, p4l = _page_hbox(row_w)
        self._wd_ks_auto = CheckBox("发布时自动勾选", p4)
        apply_instructional_tooltip(
            "勾选后发布时自动在网页上选中对应申明",
            self._wd_ks_auto,
            position=ToolTipPosition.BOTTOM,
        )
        self._wd_ks_combo = ComboBox(p4)
        apply_instructional_tooltip(
            "与快手发布页申明类选项一致",
            self._wd_ks_combo,
            position=ToolTipPosition.BOTTOM,
        )
        for val, text in KUAISHOU_CHOICES:
            self._wd_ks_combo.addItem(text, userData=val)
        self._wd_ks_combo.setFixedWidth(COMBO_WIDTH)
        p4l.addWidget(self._wd_ks_auto)
        p4l.addWidget(self._wd_ks_combo)
        p4l.addStretch(1)
        self._wd_stack.addWidget(p4)

        p5, p5l = _page_hbox(row_w)
        self._wd_xhs_attr_auto = CheckBox("属性自动勾选", p5)
        apply_instructional_tooltip(
            "勾选后发布时自动设置内容属性",
            self._wd_xhs_attr_auto,
            position=ToolTipPosition.BOTTOM,
        )
        self._wd_xhs_combo = ComboBox(p5)
        apply_instructional_tooltip(
            "小红书发布页「内容属性」选项",
            self._wd_xhs_combo,
            position=ToolTipPosition.BOTTOM,
        )
        for val, text in XHS_CONTENT_ATTR_CHOICES:
            self._wd_xhs_combo.addItem(text, userData=val)
        self._wd_xhs_combo.setFixedWidth(COMBO_WIDTH)
        p5l.addWidget(self._wd_xhs_attr_auto)
        p5l.addWidget(self._wd_xhs_combo)
        p5l.addStretch(1)
        self._wd_stack.addWidget(p5)

        self._wd_dy_combo.currentIndexChanged.connect(self._on_douyin_changed)
        self._wd_dy_auto.toggled.connect(self._on_douyin_auto_toggled)
        self._wd_ks_combo.currentIndexChanged.connect(self._on_kuaishou_changed)
        self._wd_ks_auto.toggled.connect(self._on_kuaishou_auto_toggled)
        self._wd_xhs_attr_auto.toggled.connect(self._on_xhs_attr_auto_toggled)
        self._wd_xhs_combo.currentIndexChanged.connect(self._on_xhs_content_attr_changed)

        row.addWidget(label)
        row.addWidget(self._wd_stack, 1)
        return row_w

    def refresh(
        self,
        context: AccountContext,
        cap: Optional[PublishOptionsCapabilities],
    ) -> None:
        self._context = context
        self._row_original.setVisible(True)
        self._row_work_declaration.setVisible(True)
        self._apply_original_stack_index(context)
        self._apply_work_declaration_stack_index(context, cap)
        self.sync_from_storage()
        self._update_auto_combos_enabled()

    def _apply_original_stack_index(self, context: AccountContext) -> None:
        if context == "mixed":
            self._orig_stack.setCurrentIndex(_ORIG_PAGE_MIXED)
        elif context in ("wechat_video", "xiaohongshu"):
            self._orig_stack.setCurrentIndex(_ORIG_PAGE_CHECKBOX)
        elif context == "none":
            self._orig_stack.setCurrentIndex(_ORIG_PAGE_PROMPT)
        elif context in ("douyin", "kuaishou"):
            self._orig_stack.setCurrentIndex(_ORIG_PAGE_NOT_APPLICABLE)
        else:
            self._orig_stack.setCurrentIndex(_ORIG_PAGE_PROMPT)

    def sync_from_storage(self) -> None:
        self._syncing = True
        try:
            wd = load_persisted_work_declaration()
            self._set_combo_by_data(self._wd_dy_combo, wd.get(KEY_DOUYIN))
            self._wd_dy_auto.blockSignals(True)
            self._wd_dy_auto.setChecked(bool(wd.get(KEY_DOUYIN_AUTO, False)))
            self._wd_dy_auto.blockSignals(False)

            self._set_combo_by_data(self._wd_ks_combo, wd.get(KEY_KUAISHOU))
            self._wd_ks_auto.blockSignals(True)
            self._wd_ks_auto.setChecked(bool(wd.get(KEY_KUAISHOU_AUTO, False)))
            self._wd_ks_auto.blockSignals(False)

            self._wd_xhs_attr_auto.blockSignals(True)
            self._wd_xhs_attr_auto.setChecked(bool(wd.get(KEY_XHS_CONTENT_ATTR_AUTO, False)))
            self._wd_xhs_attr_auto.blockSignals(False)
            self._set_combo_by_data(
                self._wd_xhs_combo,
                wd.get(KEY_XHS_CONTENT_ATTR),
            )

            checked = load_persisted_single_declare_original()
            if self._context == "xiaohongshu":
                checked = bool(wd.get(KEY_XHS_ORIGINAL, False))
            self._original_check.blockSignals(True)
            self._original_check.setChecked(checked)
            self._original_check.blockSignals(False)
        finally:
            self._syncing = False
            self._update_auto_combos_enabled()

    def apply_privacy_dict(self, ps: Dict[str, Any]) -> None:
        self._syncing = True
        try:
            if self._context == "wechat_video":
                self._original_check.blockSignals(True)
                self._original_check.setChecked(bool(ps.get(KEY_IS_ORIGINAL, False)))
                self._original_check.blockSignals(False)
            elif self._context == "xiaohongshu":
                self._original_check.blockSignals(True)
                self._original_check.setChecked(bool(ps.get(KEY_XHS_ORIGINAL, False)))
                self._original_check.blockSignals(False)

            dy = normalize_douyin_value(str(ps.get(KEY_DOUYIN) or "") or None)
            self._set_combo_by_data(self._wd_dy_combo, dy)
            self._wd_dy_auto.blockSignals(True)
            self._wd_dy_auto.setChecked(declaration_auto_apply(ps, KEY_DOUYIN_AUTO))
            self._wd_dy_auto.blockSignals(False)

            ks = normalize_kuaishou_value(str(ps.get(KEY_KUAISHOU) or "") or None)
            self._set_combo_by_data(self._wd_ks_combo, ks)
            self._wd_ks_auto.blockSignals(True)
            self._wd_ks_auto.setChecked(declaration_auto_apply(ps, KEY_KUAISHOU_AUTO))
            self._wd_ks_auto.blockSignals(False)

            xv = normalize_xhs_content_attr(
                str(ps.get(KEY_XHS_CONTENT_ATTR) or "") or None
            )
            self._set_combo_by_data(self._wd_xhs_combo, xv)
            self._wd_xhs_attr_auto.blockSignals(True)
            self._wd_xhs_attr_auto.setChecked(
                declaration_auto_apply(ps, KEY_XHS_CONTENT_ATTR_AUTO)
            )
            self._wd_xhs_attr_auto.blockSignals(False)
        finally:
            self._syncing = False
            self._update_auto_combos_enabled()

    def reset_to_defaults(self) -> None:
        self._original_check.blockSignals(True)
        self._original_check.setChecked(False)
        self._original_check.blockSignals(False)
        save_persisted_single_declare_original(False)

        wd = load_persisted_work_declaration()
        self._set_combo_by_data(self._wd_dy_combo, wd.get(KEY_DOUYIN))
        self._wd_dy_auto.setChecked(bool(wd.get(KEY_DOUYIN_AUTO, False)))
        self._set_combo_by_data(self._wd_ks_combo, wd.get(KEY_KUAISHOU))
        self._wd_ks_auto.setChecked(bool(wd.get(KEY_KUAISHOU_AUTO, False)))
        self._wd_xhs_attr_auto.setChecked(bool(wd.get(KEY_XHS_CONTENT_ATTR_AUTO, False)))
        self._set_combo_by_data(self._wd_xhs_combo, wd.get(KEY_XHS_CONTENT_ATTR))

    def collect_declaration_privacy(self) -> Dict[str, Any]:
        """合并原创/作品申明相关 privacy_settings 字段（不含权限、下载）。"""
        out: Dict[str, Any] = {}
        wd = load_persisted_work_declaration()

        if self._context == "wechat_video":
            out[KEY_IS_ORIGINAL] = self._original_check.isChecked()
        elif self._context == "douyin":
            raw = self._combo_current_data(self._wd_dy_combo)
            wd[KEY_DOUYIN] = normalize_douyin_value(str(raw or "") or None)
            wd[KEY_DOUYIN_AUTO] = bool(self._wd_dy_auto.isChecked())
        elif self._context == "kuaishou":
            raw = self._combo_current_data(self._wd_ks_combo)
            wd[KEY_KUAISHOU] = normalize_kuaishou_value(str(raw or "") or None)
            wd[KEY_KUAISHOU_AUTO] = bool(self._wd_ks_auto.isChecked())
        elif self._context == "xiaohongshu":
            out[KEY_XHS_ORIGINAL] = self._original_check.isChecked()
            raw = self._combo_current_data(self._wd_xhs_combo)
            wd[KEY_XHS_CONTENT_ATTR] = normalize_xhs_content_attr(str(raw or "") or None)
            wd[KEY_XHS_CONTENT_ATTR_AUTO] = bool(self._wd_xhs_attr_auto.isChecked())

        out.update(wd)
        return out

    def _apply_work_declaration_stack_index(
        self,
        context: AccountContext,
        cap: Optional[PublishOptionsCapabilities],
    ) -> None:
        if context == "none":
            self._wd_prompt_label.setText(WD_LEFT_HINT_SELECT_TARGET)
            self._wd_stack.setCurrentIndex(_WD_PAGE_PROMPT)
        elif context == "mixed":
            self._wd_stack.setCurrentIndex(_WD_PAGE_MIXED)
        elif context == "wechat_video":
            self._wd_stack.setCurrentIndex(_WD_PAGE_WECHAT)
        elif context == "douyin":
            self._wd_stack.setCurrentIndex(_WD_PAGE_DOUYIN)
        elif context == "kuaishou":
            self._wd_stack.setCurrentIndex(_WD_PAGE_KUAISHOU)
        elif context == "xiaohongshu":
            self._wd_stack.setCurrentIndex(_WD_PAGE_XIAOHONGSHU)
        else:
            self._wd_prompt_label.setText(WD_LEFT_HINT_NOT_APPLICABLE)
            self._wd_stack.setCurrentIndex(_WD_PAGE_PROMPT)

    def _update_auto_combos_enabled(self) -> None:
        self._wd_dy_combo.setEnabled(self._wd_dy_auto.isChecked())
        self._wd_ks_combo.setEnabled(self._wd_ks_auto.isChecked())
        self._wd_xhs_combo.setEnabled(self._wd_xhs_attr_auto.isChecked())

    def _on_original_changed(self) -> None:
        if self._syncing:
            return
        checked = self._original_check.isChecked()
        if self._context == "wechat_video":
            save_persisted_single_declare_original(checked)
        elif self._context == "xiaohongshu":
            cur = load_persisted_work_declaration()
            cur[KEY_XHS_ORIGINAL] = checked
            save_persisted_work_declaration(cur)

    def _on_douyin_auto_toggled(self, _checked: bool) -> None:
        self._update_auto_combos_enabled()
        self._on_douyin_changed()

    def _on_kuaishou_auto_toggled(self, _checked: bool) -> None:
        self._update_auto_combos_enabled()
        self._on_kuaishou_changed()

    def _on_xhs_attr_auto_toggled(self, _checked: bool) -> None:
        self._update_auto_combos_enabled()
        self._on_xhs_content_attr_changed()

    def _on_douyin_changed(self, *_args) -> None:
        if self._syncing:
            return
        raw = self._combo_current_data(self._wd_dy_combo)
        cur = load_persisted_work_declaration()
        cur[KEY_DOUYIN] = normalize_douyin_value(str(raw or "") or None)
        cur[KEY_DOUYIN_AUTO] = bool(self._wd_dy_auto.isChecked())
        save_persisted_work_declaration(cur)

    def _on_kuaishou_changed(self, *_args) -> None:
        if self._syncing:
            return
        raw = self._combo_current_data(self._wd_ks_combo)
        cur = load_persisted_work_declaration()
        cur[KEY_KUAISHOU] = normalize_kuaishou_value(str(raw or "") or None)
        cur[KEY_KUAISHOU_AUTO] = bool(self._wd_ks_auto.isChecked())
        save_persisted_work_declaration(cur)

    def _on_xhs_content_attr_changed(self, *_args) -> None:
        if self._syncing:
            return
        raw = self._combo_current_data(self._wd_xhs_combo)
        cur = load_persisted_work_declaration()
        cur[KEY_XHS_CONTENT_ATTR] = normalize_xhs_content_attr(str(raw or "") or None)
        cur[KEY_XHS_CONTENT_ATTR_AUTO] = bool(self._wd_xhs_attr_auto.isChecked())
        save_persisted_work_declaration(cur)

    @staticmethod
    def _combo_current_data(combo: ComboBox) -> Any:
        raw = combo.currentData()
        if raw is None and combo.currentIndex() >= 0:
            raw = combo.itemData(combo.currentIndex())
        return raw

    @staticmethod
    def _set_combo_by_data(combo: ComboBox, value: Any) -> None:
        combo.blockSignals(True)
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                break
        combo.blockSignals(False)
