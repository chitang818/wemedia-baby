"""工作台图表 loading / reveal 行为"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.ui.components.charts import ChartLoadState, _apply_chart_animation
from src.ui.workspace_chart_animation_prefs import (
    CHART_ENTRY_ANIMATION_MS,
    CHART_OVERLAY_FADE_MS,
)


def test_apply_chart_animation_duration_when_enabled():
    chart = MagicMock()
    _apply_chart_animation(chart, animate=True)
    chart.setAnimationDuration.assert_called_once_with(CHART_ENTRY_ANIMATION_MS)
    chart.setAnimationOptions.assert_called()

    chart.reset_mock()
    _apply_chart_animation(chart, animate=False)
    chart.setAnimationOptions.assert_called()


def test_reveal_with_data_skips_overlay_when_not_visible():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from src.ui.components.charts import PlatformDistributionChart

    chart = PlatformDistributionChart()
    calls: list[bool] = []

    def apply_fn(*, animate: bool = False) -> None:
        calls.append(animate)

    chart.reveal_with_data(apply_fn, animate_entry=True)
    assert ChartLoadState.READY == chart._load_state
    assert calls == [True]


def test_reveal_with_data_hides_overlay_when_loading():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from src.ui.components.charts import PlatformDistributionChart

    chart = PlatformDistributionChart()
    chart.show_loading()
    assert chart.is_loading

    calls: list[bool] = []

    def apply_fn(*, animate: bool = False) -> None:
        calls.append(animate)

    with patch.object(chart._loading_overlay, "hide_animated"):
        chart.reveal_with_data(apply_fn, animate_entry=False)
    from PySide6.QtTest import QTest

    QTest.qWait(CHART_OVERLAY_FADE_MS + 50)
    assert calls == [False]
    assert chart._load_state == ChartLoadState.READY


def test_workspace_chart_prefs_sane_defaults():
    assert CHART_OVERLAY_FADE_MS >= 100
    assert 200 <= CHART_ENTRY_ANIMATION_MS <= 600
