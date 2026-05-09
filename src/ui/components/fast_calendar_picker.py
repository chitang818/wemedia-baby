"""
QFluentWidgets FastCalendarPicker 统一配置。
与 CalendarPicker API 一致，弹出更快、占用更小，见官方文档：
https://qfluentwidgets.com/zh/pages/components/calendarpicker/#fastcalendarpicker
"""
from typing import Optional

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QSizePolicy, QWidget

from qfluentwidgets import FastCalendarPicker, FlyoutAnimationType


def create_fast_calendar_picker(
    parent: QWidget,
    *,
    initial_date: Optional[QDate] = None,
    date_format: str = "yyyy年M月d日",
    minimum_width: int = 118,
    maximum_width: int = 152,
) -> FastCalendarPicker:
    picker = FastCalendarPicker(parent)
    picker.setDateFormat(date_format)
    picker.setMinimumWidth(minimum_width)
    picker.setMaximumWidth(maximum_width)
    # 避免在 QFormLayout 等布局里被横向拉伸占满整列
    picker.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    try:
        picker.setFlyoutAnimationType(FlyoutAnimationType.DROP_DOWN)
    except Exception:
        pass
    if initial_date is not None and initial_date.isValid():
        picker.setDate(initial_date)
    return picker
