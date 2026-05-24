"""Workspace-specific Fluent scroll area helpers."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget

try:
    from qfluentwidgets import SmoothScrollArea as _FluentScrollArea
except Exception:
    try:
        from qfluentwidgets import ScrollArea as _FluentScrollArea
    except Exception:
        _FluentScrollArea = QScrollArea


def create_workspace_scroll_area(parent: Optional[QWidget] = None) -> QScrollArea:
    """Create a transparent Fluent-style scroll area for workspace panels."""
    scroll_area = _FluentScrollArea(parent)
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.NoFrame)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    scroll_area.viewport().setStyleSheet("background: transparent;")

    if hasattr(scroll_area, "enableTransparentBackground"):
        try:
            scroll_area.enableTransparentBackground()
        except Exception:
            pass

    if hasattr(scroll_area, "setScrollAnimation"):
        try:
            scroll_area.setScrollAnimation(Qt.Vertical, 320, QEasingCurve.OutCubic)
            scroll_area.setScrollAnimation(Qt.Horizontal, 320, QEasingCurve.OutCubic)
        except Exception:
            pass

    try:
        scroll_area.verticalScrollBar().setSingleStep(32)
    except Exception:
        pass

    return scroll_area


def set_workspace_scroll_content(scroll_area: QScrollArea, content: QWidget) -> None:
    """Attach transparent content to a workspace scroll area."""
    content.setStyleSheet("background: transparent;")
    scroll_area.setWidget(content)
