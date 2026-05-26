# -*- coding: utf-8 -*-
"""
单条发布页「更多发布设置」卡片（并行开发版）。

文件：more_publish_settings_card.py
类名：MorePublishSettingsCard

设计目标：
- 左栏：位置、带货推广、设置权限、原创声明、作品申明。
- 右栏：按所选平台/账号组条件展示特殊项（如抖音打卡/带货模式、图文音乐等）。
- 完善后切换提交/回填并删除下方旧版「发布设置」卡片。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Set

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    LineEdit,
    SubtitleLabel,
)

from src.domain.publish.location_settings import (
    LOCATION_MODE_CHECKIN,
    LOCATION_MODE_CHOICES,
)
from src.domain.publish.single_publish_options_capabilities import (
    PublishOptionsCapabilities,
    capabilities_for_platform,
)
from src.ui.publish.location import LocationSelectorWidget, WechatVideoLocationOption
from src.ui.publish.promotion import CartSelectorWidget

from .declaration_settings_panel import DeclarationSettingsPanel
from .group_platform_declaration_panel import GroupPlatformDeclarationPanel
from .constants import (
    SHARED_LEFT_COMBO_WIDTH,
    H_GAP,
    LABEL_WIDTH,
    LOCATION_LINEEDIT_MAX_WIDTH,
    LOCATION_MODE_COMBO_WIDTH,
    LOCATION_MODE_TAG_KEY,
    ROW_GAP,
    SHARED_ROW_MIN_HEIGHT,
    DIVIDER_COLOR,
    DIVIDER_WIDTH,
    DOUYIN_LOC_PROMO_MUTEX_HINT_WHEN_LOCATION,
    DOUYIN_LOC_PROMO_MUTEX_HINT_WHEN_PROMOTION,
    DOUYIN_LOCATION_SPECIAL_LABEL,
    DOUYIN_LOCATION_SPECIAL_LABEL_STYLE,
    DOUYIN_LOCATION_SPECIAL_LABEL_WIDTH,
    SPLIT_COLUMN_GAP,
    SPLIT_LEFT_STRETCH,
    SPLIT_RIGHT_STRETCH,
    TAG_TYPE_COMBO_WIDTH,
)

AccountContext = str  # platform_id | "none" | "mixed"


class MorePublishSettingsCard(CardWidget):
    """更多发布设置：左栏共用项 + 竖线 + 右栏平台特殊项。"""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        is_image_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self._is_image_mode = is_image_mode
        self._tag_values: Dict[str, str] = {
            "位置": "",
            LOCATION_MODE_TAG_KEY: "",
        }
        self._platform_id_for_location: str = ""
        self._includes_douyin: bool = False
        self._last_refresh_context: AccountContext = "none"
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(ROW_GAP)

        title_row = QHBoxLayout()
        title = SubtitleLabel("更多发布设置", self)
        hint = BodyLabel("开发中：完善后将替代下方「发布设置」", self)
        hint.setStyleSheet("color: #888; font-size: 12px;")
        title_row.addWidget(title)
        title_row.addSpacing(12)
        title_row.addWidget(hint, 1)
        root.addLayout(title_row)

        root.addWidget(self._build_split_body(), 1)

    def _make_vertical_divider(self, parent: QWidget) -> QWidget:
        wrap = QWidget(parent)
        wrap.setObjectName("morePublishSettingsDividerWrap")
        wrap.setFixedWidth(DIVIDER_WIDTH)
        wrap.setMinimumHeight(100)
        wrap.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        wrap.setStyleSheet(
            f"#morePublishSettingsDividerWrap {{ background-color: {DIVIDER_COLOR}; }}"
        )
        return wrap

    def _build_split_body(self) -> QWidget:
        body = QWidget(self)
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(body)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self._panel_shared = QWidget(body)
        self._panel_shared.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        shared_layout = QVBoxLayout(self._panel_shared)
        shared_layout.setContentsMargins(0, 0, 0, 0)
        shared_layout.setSpacing(ROW_GAP)

        self._row_location = self._finalize_settings_row(self._build_location_row())
        shared_layout.addWidget(self._row_location)
        self._row_promotion = self._finalize_settings_row(self._build_promotion_row())
        shared_layout.addWidget(self._row_promotion)
        self._row_privacy = self._finalize_settings_row(self._build_privacy_row())
        shared_layout.addWidget(self._row_privacy)
        self._declaration_panel = DeclarationSettingsPanel(self._panel_shared)
        shared_layout.addWidget(self._declaration_panel)
        shared_layout.addStretch(1)

        self._right_column_wrap = QWidget(body)
        right_col = QHBoxLayout(self._right_column_wrap)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(SPLIT_COLUMN_GAP)
        self._split_divider = self._make_vertical_divider(self._right_column_wrap)
        right_col.addWidget(self._split_divider)

        self._panel_platform = QWidget(self._right_column_wrap)
        self._panel_platform.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        platform_outer = QVBoxLayout(self._panel_platform)
        platform_outer.setContentsMargins(0, 0, 0, 0)
        platform_outer.setSpacing(ROW_GAP)
        platform_outer.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._douyin_location_extras = self._finalize_settings_row(
            self._build_douyin_location_extras()
        )
        platform_outer.addWidget(self._douyin_location_extras)
        self._group_declaration_panel = GroupPlatformDeclarationPanel(
            self._panel_platform, is_image_mode=self._is_image_mode
        )
        platform_outer.addWidget(self._group_declaration_panel)
        platform_outer.addWidget(self._build_platform_section())
        platform_outer.addStretch(1)
        right_col.addWidget(self._panel_platform, 1)

        row.addWidget(self._panel_shared, SPLIT_LEFT_STRETCH)
        row.addWidget(self._right_column_wrap, SPLIT_RIGHT_STRETCH)
        return body

    @staticmethod
    def _finalize_settings_row(row_w: QWidget) -> QWidget:
        row_w.setMinimumHeight(SHARED_ROW_MIN_HEIGHT)
        lay = row_w.layout()
        if isinstance(lay, QHBoxLayout):
            lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        return row_w

    def _build_location_row(self) -> QWidget:
        row_w = QWidget(self)
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(H_GAP)
        label = BodyLabel("位置设置", row_w)
        label.setFixedWidth(LABEL_WIDTH)

        self._location_selector = LocationSelectorWidget(row_w)
        self._location_selector.set_combo_fixed_width(SHARED_LEFT_COMBO_WIDTH)
        self._location_selector.selection_changed.connect(
            self._on_location_selector_changed
        )
        self._location_content_edit = LineEdit(row_w)
        self._location_content_edit.setMaximumWidth(LOCATION_LINEEDIT_MAX_WIDTH)
        self._location_content_edit.hide()

        self._wx_empty_loc = WechatVideoLocationOption(row_w)
        self._wx_empty_loc.attach_line_edit(self._location_content_edit)

        row.addWidget(label)
        row.addWidget(self._location_selector, 0)
        row.addWidget(self._location_content_edit, 1)
        row.addWidget(self._wx_empty_loc.widget(), 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        return row_w

    def _build_douyin_location_extras(self) -> QWidget:
        """抖音位置特殊项：左标签 + 右打卡/带货模式（仅右栏展示）。"""
        wrap = QWidget(self._panel_platform)
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(H_GAP)

        self._douyin_location_special_label = BodyLabel(DOUYIN_LOCATION_SPECIAL_LABEL, wrap)
        self._douyin_location_special_label.setStyleSheet(DOUYIN_LOCATION_SPECIAL_LABEL_STYLE)
        self._douyin_location_special_label.setFixedWidth(DOUYIN_LOCATION_SPECIAL_LABEL_WIDTH)

        self._location_mode_combo = ComboBox(wrap)
        self._location_mode_combo.addItems(list(LOCATION_MODE_CHOICES))
        self._location_mode_combo.setFixedWidth(LOCATION_MODE_COMBO_WIDTH)
        self._location_mode_combo.currentTextChanged.connect(self._on_location_mode_changed)

        row.addWidget(self._douyin_location_special_label)
        row.addWidget(self._location_mode_combo)
        row.addStretch(1)
        wrap.hide()
        return wrap

    def _build_promotion_row(self) -> QWidget:
        row_w = QWidget(self)
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(H_GAP)
        label = BodyLabel("带货推广", row_w)
        label.setFixedWidth(LABEL_WIDTH)

        self._promotion_type_combo = ComboBox(row_w)
        self._promotion_type_combo.addItems(["无", "购物车推广", "团购推广"])
        self._promotion_type_combo.setFixedWidth(SHARED_LEFT_COMBO_WIDTH)
        self._promotion_type_combo.currentTextChanged.connect(
            self._on_promotion_type_changed
        )

        self._yellow_cart_selector = CartSelectorWidget(row_w)
        self._yellow_cart_selector.hide()

        self._promo_placeholder = BodyLabel("功能开发中，敬请期待", row_w)
        self._promo_placeholder.setStyleSheet("color: #888; font-size: 12px;")
        self._promo_placeholder.hide()

        self._douyin_loc_promo_hint = BodyLabel("", row_w)
        self._douyin_loc_promo_hint.setStyleSheet("color: #c45656; font-size: 12px;")
        self._douyin_loc_promo_hint.hide()

        row.addWidget(label)
        row.addWidget(self._promotion_type_combo)
        row.addWidget(self._yellow_cart_selector, 1)
        row.addWidget(self._promo_placeholder)
        row.addWidget(self._douyin_loc_promo_hint, 1)
        row.addStretch(1)
        return row_w

    def _build_privacy_row(self) -> QWidget:
        row_w = QWidget(self)
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(H_GAP)
        label = BodyLabel("设置权限", row_w)
        label.setFixedWidth(LABEL_WIDTH)

        self._privacy_combo = ComboBox(row_w)
        self._privacy_combo.addItems(["公开可见", "好友可见", "私密"])
        self._privacy_combo.setFixedWidth(SHARED_LEFT_COMBO_WIDTH)

        save_label = "允许他人保存作品" if self._is_image_mode else "允许保存视频"
        self._allow_download_check = CheckBox(save_label, row_w)
        self._allow_download_check.setChecked(True)

        row.addWidget(label)
        row.addWidget(self._privacy_combo)
        row.addWidget(self._allow_download_check)
        row.addStretch(1)
        return row_w

    def _build_platform_section(self) -> QWidget:
        section = QWidget(self._panel_platform)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ROW_GAP)

        self._platform_section_title = SubtitleLabel("平台相关设置", section)
        layout.addWidget(self._platform_section_title)

        self._platform_content = QWidget(section)
        pc_layout = QVBoxLayout(self._platform_content)
        pc_layout.setContentsMargins(0, 0, 0, 0)
        pc_layout.setSpacing(ROW_GAP)

        self._row_music = self._finalize_settings_row(self._build_music_row())
        pc_layout.addWidget(self._row_music)

        self._platform_content.hide()
        layout.addWidget(self._platform_content)
        section.hide()
        return section

    def _build_music_row(self) -> QWidget:
        row_w = QWidget(self._platform_content)
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(H_GAP)
        label = BodyLabel("选择音乐", row_w)
        label.setFixedWidth(LABEL_WIDTH)

        self._music_type_combo = ComboBox(row_w)
        self._music_type_combo.addItems(["不选音乐", "随机音乐", "指定音乐"])
        self._music_type_combo.setFixedWidth(TAG_TYPE_COMBO_WIDTH + 16)

        self._music_name_edit = LineEdit(row_w)
        self._music_name_edit.setPlaceholderText("请输入音乐名称")
        self._music_name_edit.hide()

        row.addWidget(label)
        row.addWidget(self._music_type_combo)
        row.addWidget(self._music_name_edit, 1)
        row.addStretch(1)
        return row_w

    def refresh(
        self,
        context: AccountContext,
        *,
        location_platform: str = "",
        platforms_in_selection: Optional[Set[str]] = None,
    ) -> None:
        """根据账号上下文与涉及平台集合刷新显隐。"""
        self._platform_id_for_location = (location_platform or "").strip()
        if self._platform_id_for_location:
            self._location_selector.set_platform(self._platform_id_for_location)

        normalized = {
            (p or "").strip().lower()
            for p in (platforms_in_selection or ())
            if (p or "").strip()
        }
        self._includes_douyin = "douyin" in normalized
        self._last_refresh_context = context

        cap: Optional[PublishOptionsCapabilities] = None
        if context not in ("none", "mixed"):
            cap = capabilities_for_platform(context, is_image_mode=self._is_image_mode)

        self._apply_shared_rows(cap, context)
        self._declaration_panel.refresh(context, cap)
        self._group_declaration_panel.refresh(context, normalized)
        self._apply_right_column(
            cap,
            context,
            includes_douyin=self._includes_douyin,
            platforms_in_selection=normalized,
        )
        self._apply_douyin_location_promotion_mutex()

    def collect_extension_fields(self) -> Dict[str, Any]:
        ctx = getattr(self, "_last_refresh_context", "none")
        if ctx == "mixed":
            decl = self._group_declaration_panel.collect_declaration_privacy()
        else:
            decl = self._declaration_panel.collect_declaration_privacy()
        return {
            "tag_values": dict(self._tag_values),
            "privacy_text": self._privacy_combo.currentText(),
            "allow_download": self._allow_download_check.isChecked(),
            "promotion_type": self._promotion_type_combo.currentText(),
            "location_short": self._location_selector.get_selected_short_name(),
            "declaration_privacy": decl,
        }

    def reset_to_defaults(self) -> None:
        self._tag_values = {
            "位置": "",
            LOCATION_MODE_TAG_KEY: "",
        }
        self._promotion_type_combo.setCurrentIndex(0)
        self._yellow_cart_selector.apply_record("")
        self._privacy_combo.setCurrentIndex(0)
        self._allow_download_check.setChecked(True)
        self._location_selector.apply_record("")
        self._declaration_panel.reset_to_defaults()
        self._group_declaration_panel.reset_to_defaults()
        self.refresh("none", platforms_in_selection=set())

    def apply_declaration_from_privacy_dict(self, ps: Dict[str, Any]) -> None:
        """编辑回填：从 privacy_settings 恢复原创/作品申明控件。"""
        self._declaration_panel.apply_privacy_dict(ps)
        self._group_declaration_panel.apply_privacy_dict(ps)

    def _sync_location_mode_from_tag_values(self) -> None:
        raw = (self._tag_values.get(LOCATION_MODE_TAG_KEY) or "").strip()
        mode = raw if raw in LOCATION_MODE_CHOICES else LOCATION_MODE_CHECKIN
        self._tag_values[LOCATION_MODE_TAG_KEY] = mode
        self._location_mode_combo.blockSignals(True)
        self._location_mode_combo.setCurrentText(mode)
        self._location_mode_combo.blockSignals(False)

    def _on_location_mode_changed(self, text: str) -> None:
        if text in LOCATION_MODE_CHOICES:
            self._tag_values[LOCATION_MODE_TAG_KEY] = text

    def _on_location_selector_changed(self) -> None:
        sn = self._location_selector.get_selected_short_name()
        self._tag_values["位置"] = sn
        if self._includes_douyin and sn:
            self._clear_promotion_to_none()
        self._apply_douyin_location_promotion_mutex()

    def _on_promotion_type_changed(self, text: str) -> None:
        if self._includes_douyin and text != "无":
            if self._location_selector.get_selected_short_name():
                self._location_selector.apply_record("")
                self._tag_values["位置"] = ""
        self._sync_promotion_subcontrols(text)
        self._apply_douyin_location_promotion_mutex()

    def _clear_promotion_to_none(self) -> None:
        if self._promotion_type_combo.currentText() == "无":
            return
        self._promotion_type_combo.blockSignals(True)
        self._promotion_type_combo.setCurrentIndex(0)
        self._promotion_type_combo.blockSignals(False)
        self._yellow_cart_selector.apply_record("")
        self._sync_promotion_subcontrols("无")

    def _apply_douyin_location_promotion_mutex(self) -> None:
        """抖音：位置推广与带货推广互斥（与创作者中心「添加标签」规则一致）。"""
        if not self._includes_douyin:
            self._promotion_type_combo.setEnabled(True)
            self._location_selector.setEnabled(True)
            self._douyin_loc_promo_hint.hide()
            return

        has_location = bool(self._location_selector.get_selected_short_name())
        has_promotion = self._promotion_type_combo.currentText() != "无"

        if has_location:
            self._promotion_type_combo.setEnabled(False)
            self._yellow_cart_selector.setEnabled(False)
            self._promo_placeholder.setEnabled(False)
            self._location_selector.setEnabled(True)
            self._douyin_loc_promo_hint.setText(DOUYIN_LOC_PROMO_MUTEX_HINT_WHEN_LOCATION)
            self._douyin_loc_promo_hint.show()
        elif has_promotion:
            self._promotion_type_combo.setEnabled(True)
            self._yellow_cart_selector.setEnabled(True)
            self._promo_placeholder.setEnabled(True)
            self._location_selector.setEnabled(False)
            self._douyin_loc_promo_hint.setText(DOUYIN_LOC_PROMO_MUTEX_HINT_WHEN_PROMOTION)
            self._douyin_loc_promo_hint.show()
        else:
            self._promotion_type_combo.setEnabled(True)
            self._yellow_cart_selector.setEnabled(True)
            self._promo_placeholder.setEnabled(True)
            self._location_selector.setEnabled(True)
            self._douyin_loc_promo_hint.hide()

    def _sync_promotion_subcontrols(self, _text: str = "") -> None:
        promo_text = self._promotion_type_combo.currentText()
        self._yellow_cart_selector.setVisible(promo_text == "购物车推广")
        self._promo_placeholder.setVisible(promo_text == "团购推广")

    def _apply_shared_rows(
        self,
        cap: Optional[PublishOptionsCapabilities],
        context: AccountContext,
    ) -> None:
        self._row_location.setVisible(True)
        self._row_promotion.setVisible(True)
        self._row_privacy.setVisible(True)
        self._privacy_combo.setVisible(True)
        self._allow_download_check.setVisible(True)

        show_wx = context == "wechat_video" or bool(
            cap and cap.show_wechat_empty_location
        )
        self._wx_empty_loc.set_row_visible(show_wx)
        self._sync_promotion_subcontrols()

    def _platform_section_has_content(
        self,
        cap: Optional[PublishOptionsCapabilities],
        context: AccountContext,
    ) -> bool:
        if context in ("none", "mixed") or cap is None:
            return False
        return bool(cap.show_music)

    def _apply_right_column(
        self,
        cap: Optional[PublishOptionsCapabilities],
        context: AccountContext,
        *,
        includes_douyin: bool,
        platforms_in_selection: Optional[Set[str]] = None,
    ) -> None:
        has_music_block = self._platform_section_has_content(cap, context)
        plats = platforms_in_selection or set()
        has_group_decl = (
            context == "mixed"
            and self._group_declaration_panel.has_content(plats)
        )
        has_right = includes_douyin or has_music_block or has_group_decl

        self._right_column_wrap.setVisible(has_right)
        if not has_right:
            return

        self._douyin_location_extras.setVisible(includes_douyin)
        if includes_douyin:
            self._sync_location_mode_from_tag_values()

        section = self._platform_section_title.parentWidget()
        if has_music_block:
            assert cap is not None and section is not None
            section.show()
            self._platform_section_title.show()
            self._platform_content.show()
            self._row_music.setVisible(cap.show_music)
        elif section is not None:
            section.hide()
