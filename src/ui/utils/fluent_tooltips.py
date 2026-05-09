"""
为控件启用 QFluentWidgets 自绘悬停提示，替代 Windows 上易出现的原生 QToolTip 黑底深字问题。

用法：对任意已 setToolTip 的 QWidget 调用 install_fluent_tool_tip(widget)；
或一次性绑定文案并安装：apply_instructional_tooltip(text, widget, ...)。

ToolTipPosition / ToolTipFilter 仅从本模块的单一深层 import 引入，业务代码请：
    from src.ui.utils.fluent_tooltips import ToolTipPosition, install_fluent_tool_tip, apply_instructional_tooltip
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget

from qfluentwidgets.components.widgets.tool_tip import ToolTipFilter, ToolTipPosition

__all__ = [
    "ToolTipPosition",
    "ToolTipFilter",
    "install_fluent_tool_tip",
    "apply_instructional_tooltip",
]


def apply_instructional_tooltip(
    text: str,
    *widgets: QWidget,
    show_delay_ms: int = 400,
    position: ToolTipPosition = ToolTipPosition.BOTTOM,
) -> None:
    """对多个控件绑定同一说明文案，并启用 Fluent ToolTip。"""
    for w in widgets:
        if w is None:
            continue
        w.setToolTip(text)
        install_fluent_tool_tip(
            w, show_delay_ms=show_delay_ms, position=position
        )


def install_fluent_tool_tip(
    widget: QWidget,
    *,
    show_delay_ms: int = 400,
    position: ToolTipPosition = ToolTipPosition.BOTTOM,
) -> Optional[ToolTipFilter]:
    """安装事件过滤器：拦截原生 ToolTip，延迟后显示 Fluent ToolTip 样式。"""
    if widget is None:
        return None
    if getattr(widget, "_fluent_tool_tip_filter", None) is not None:
        return widget._fluent_tool_tip_filter  # type: ignore[attr-defined]
    filt = ToolTipFilter(widget, show_delay_ms, position)
    widget.installEventFilter(filt)
    setattr(widget, "_fluent_tool_tip_filter", filt)
    return filt
