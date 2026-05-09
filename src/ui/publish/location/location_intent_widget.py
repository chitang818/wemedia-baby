# -*- coding: utf-8 -*-
"""单条发布页：位置「需要输入 / 不需要输入」+ 视频号子选项（保留默认 / 不展示）。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QButtonGroup, QVBoxLayout, QWidget

from qfluentwidgets import BodyLabel, CaptionLabel, RadioButton

from src.domain.publish.location_settings import (
    LocationPoiInputChoice,
    WechatNoPoiSubchoice,
    dialog_state_from_persisted,
)


class LocationIntentRowWidget(QWidget):
    """放在扩展信息卡片内，与「添加标签」行配合使用。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._wechat_capable = False

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(6)
        v.addWidget(BodyLabel("位置方式", self))
        self.rb_need = RadioButton("需要输入位置", self)
        self.rb_no = RadioButton("不需要输入位置", self)
        grp = QButtonGroup(self)
        grp.addButton(self.rb_need)
        grp.addButton(self.rb_no)
        v.addWidget(self.rb_need)
        v.addWidget(self.rb_no)

        self.wx_wrap = QWidget(self)
        wx_l = QVBoxLayout(self.wx_wrap)
        wx_l.setContentsMargins(20, 0, 0, 0)
        wx_l.setSpacing(4)
        wx_l.addWidget(
            CaptionLabel(
                "在「不需要输入位置」时，下列两项仅对视频号生效；其他平台以是否填写位置为准。",
                self,
            )
        )
        self.rb_wx_keep = RadioButton("保留发布页上的位置（如当地城市）", self)
        self.rb_wx_hide = RadioButton("不在作品里展示位置（发布页选「不显示位置」）", self)
        g2 = QButtonGroup(self.wx_wrap)
        g2.addButton(self.rb_wx_keep)
        g2.addButton(self.rb_wx_hide)
        wx_l.addWidget(self.rb_wx_keep)
        wx_l.addWidget(self.rb_wx_hide)
        v.addWidget(self.wx_wrap)

        self.rb_need.toggled.connect(self._on_main_toggled)
        self.rb_no.toggled.connect(self._on_main_toggled)
        self.rb_need.setChecked(True)
        self.rb_wx_keep.setChecked(True)
        self._on_main_toggled()

    def _on_main_toggled(self) -> None:
        need = self.rb_need.isChecked()
        self.wx_wrap.setVisible((not need) and self._wechat_capable)

    def set_wechat_capable(self, capable: bool) -> None:
        self._wechat_capable = bool(capable)
        self._on_main_toggled()

    def is_need_input(self) -> bool:
        return self.rb_need.isChecked()

    def apply_state(
        self,
        *,
        poi_info_storage: str,
        wx_raw: Optional[bool],
        show_wechat_sub: bool,
    ) -> None:
        self.set_wechat_capable(show_wechat_sub)
        need, sub = dialog_state_from_persisted(
            poi_info_storage,
            wx_raw,
            show_wechat_subchoice=show_wechat_sub,
        )
        self.rb_need.setChecked(need == LocationPoiInputChoice.NEED_INPUT)
        self.rb_no.setChecked(need == LocationPoiInputChoice.NO_INPUT)
        if sub == WechatNoPoiSubchoice.HIDE_LOCATION:
            self.rb_wx_hide.setChecked(True)
        else:
            self.rb_wx_keep.setChecked(True)
        self._on_main_toggled()

    def effective_wx_empty_poi_flag(self) -> bool:
        """与空 POI 配套写入 wechat_empty_location_open_picker：True=去选不显示位置。"""
        if self.rb_need.isChecked():
            return False
        if not self._wechat_capable:
            return False
        return bool(self.rb_wx_hide.isChecked())
