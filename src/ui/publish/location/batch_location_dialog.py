# -*- coding: utf-8 -*-
"""批量公共位置设置弹窗：需要/不需要输入位置；选「不需要」时始终出现视频号专用二选一（仅视频号发布生效）。"""
from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import BodyLabel, CaptionLabel, ComboBox, RadioButton

from src.domain.publish.location_settings import (
    LOCATION_MODE_CHECKIN,
    LOCATION_MODE_CHOICES,
    LocationPoiInputChoice,
    LocationPublishFields,
    WechatNoPoiSubchoice,
    dialog_state_from_persisted,
    location_publish_fields_from_intent,
    parse_location_short_name_from_storage,
    parse_poi_info_storage,
)
from src.ui.components.base_dialog import StandardBaseDialog
from src.ui.publish.location.location_selector_widget import LocationSelectorWidget


class BatchLocationDialog(StandardBaseDialog):
    """确定后返回 ``(poi_info, wechat_empty_location_open_picker)``，与批量页状态一致。"""

    def __init__(
        self,
        parent=None,
        *,
        poi_info_initial: str = "",
        wx_pick_initial: Optional[bool] = None,
        show_wechat_no_poi_subchoice: bool = False,
    ) -> None:
        super().__init__(parent, title="位置设置")
        self.widget.setMinimumWidth(460)
        self._show_wx_sub = bool(show_wechat_no_poi_subchoice)

        need, sub = dialog_state_from_persisted(
            poi_info_initial,
            wx_pick_initial,
            show_wechat_subchoice=self._show_wx_sub,
        )
        loc_short = parse_location_short_name_from_storage(poi_info_initial)
        _, loc_mode = parse_poi_info_storage(poi_info_initial)
        if loc_mode not in LOCATION_MODE_CHOICES:
            loc_mode = LOCATION_MODE_CHECKIN

        root = QVBoxLayout()
        root.setSpacing(10)
        root.setContentsMargins(0, 0, 0, 0)

        root.addWidget(BodyLabel("位置信息", self.widget))

        self._rb_need = RadioButton("需要输入位置", self.widget)
        self._rb_no = RadioButton("不需要输入位置", self.widget)
        self._grp_main = QButtonGroup(self.widget)
        self._grp_main.addButton(self._rb_need)
        self._grp_main.addButton(self._rb_no)
        root.addWidget(self._rb_need)
        root.addWidget(self._rb_no)

        self._need_wrap = QWidget(self.widget)
        need_lay = QVBoxLayout(self._need_wrap)
        need_lay.setContentsMargins(20, 0, 0, 8)
        need_lay.setSpacing(8)
        r1 = QHBoxLayout()
        r1.setSpacing(12)
        r1.addWidget(BodyLabel("选择位置", self.widget))
        self._location_selector = LocationSelectorWidget(
            self.widget, initial_short_name=loc_short
        )
        r1.addWidget(self._location_selector, 1)
        need_lay.addLayout(r1)
        r2 = QHBoxLayout()
        r2.setSpacing(12)
        r2.addWidget(BodyLabel("位置模式", self.widget))
        self.mode_combo = ComboBox(self.widget)
        self.mode_combo.addItems(list(LOCATION_MODE_CHOICES))
        self.mode_combo.setCurrentText(loc_mode)
        r2.addWidget(self.mode_combo, 1)
        need_lay.addLayout(r2)
        need_lay.addWidget(
            CaptionLabel(
                "请先在「带货推广 → 位置推广」配置各平台搜索词，再在此选择位置简称。",
                self.widget,
            )
        )
        root.addWidget(self._need_wrap)

        self._wx_wrap = QWidget(self.widget)
        wx_lay = QVBoxLayout(self._wx_wrap)
        wx_lay.setContentsMargins(20, 0, 0, 0)
        wx_lay.setSpacing(6)
        wx_lay.addWidget(
            CaptionLabel(
                "主选项仍是上文的「需要 / 不需要输入位置」。以下两项仅对本次批量中的视频号生效；"
                "其他平台只看是否填写地理位置即可。",
                self.widget,
            )
        )
        self._rb_wx_keep = RadioButton(
            "保留发布页上的位置（如当地城市，不在发布页点「不显示位置」）",
            self.widget,
        )
        self._rb_wx_hide = RadioButton(
            "不在作品里展示位置（发布时在页面选择「不显示位置」）",
            self.widget,
        )
        self._grp_wx = QButtonGroup(self.widget)
        self._grp_wx.addButton(self._rb_wx_keep)
        self._grp_wx.addButton(self._rb_wx_hide)
        wx_lay.addWidget(self._rb_wx_keep)
        wx_lay.addWidget(self._rb_wx_hide)
        root.addWidget(self._wx_wrap)
        self._wx_wrap.setVisible(False)

        self.viewLayout.addLayout(root)

        if need == LocationPoiInputChoice.NEED_INPUT:
            self._rb_need.setChecked(True)
        else:
            self._rb_no.setChecked(True)
        if sub == WechatNoPoiSubchoice.HIDE_LOCATION:
            self._rb_wx_hide.setChecked(True)
        else:
            self._rb_wx_keep.setChecked(True)

        self._rb_need.toggled.connect(self._sync_visibility)
        self._rb_no.toggled.connect(self._sync_visibility)
        self._sync_visibility()

    def _sync_visibility(self) -> None:
        need = self._rb_need.isChecked()
        self._need_wrap.setVisible(need)
        self._wx_wrap.setVisible((not need) and self._show_wx_sub)

    def accept(self) -> None:
        if self._rb_need.isChecked():
            poi = self._location_selector.build_poi_info_storage(
                self.mode_combo.currentText().strip()
            )
            if not (poi or "").strip():
                from qfluentwidgets import InfoBar, InfoBarPosition

                InfoBar.warning(
                    "请选择位置",
                    "已选择「需要输入位置」时，请从位置推广库选择位置，或改选「不需要输入位置」。"
                    "若列表为空，请先到「带货推广 → 位置推广」添加配置。",
                    parent=self.window() or self,
                    position=InfoBarPosition.TOP,
                    duration=4000,
                )
                return
        super().accept()

    def outcome(self) -> Tuple[str, Optional[bool]]:
        if self._rb_need.isChecked():
            poi = self._location_selector.build_poi_info_storage(
                self.mode_combo.currentText().strip()
            )
            fields = LocationPublishFields(
                poi_info=poi,
                wechat_empty_location_open_picker=False,
            )
        else:
            sub = (
                WechatNoPoiSubchoice.HIDE_LOCATION
                if self._show_wx_sub and self._rb_wx_hide.isChecked()
                else WechatNoPoiSubchoice.KEEP_PAGE_DEFAULT
                if self._show_wx_sub
                else WechatNoPoiSubchoice.NOT_APPLICABLE
            )
            fields = location_publish_fields_from_intent(
                input_choice=LocationPoiInputChoice.NO_INPUT,
                wechat_sub=sub,
                loc_text="",
                loc_mode="",
            )
        d = fields.to_common_fields_dict()
        return str(d.get("poi_info") or ""), d.get("wechat_empty_location_open_picker")
