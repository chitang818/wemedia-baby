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


def test_platform_distribution_rows_are_sorted_and_percented():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from src.ui.components.charts import PlatformDistributionChart

    rows = PlatformDistributionChart.build_distribution_rows(
        {"快手": 2, "抖音": 8, "视频号": 0}
    )

    assert [row["platform"] for row in rows] == ["抖音", "快手"]
    assert rows[0]["count"] == 8
    assert rows[0]["percent"] == pytest.approx(80.0)
    assert rows[1]["percent"] == pytest.approx(20.0)


def test_platform_distribution_collapsed_rows_merge_other_when_too_many():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from src.ui.components.charts import PlatformDistributionChart

    rows = PlatformDistributionChart.build_collapsed_rows(
        {
            "平台A": 9,
            "平台B": 8,
            "平台C": 7,
            "平台D": 6,
            "平台E": 5,
            "平台F": 4,
            "平台G": 3,
        }
    )

    assert len(rows) == 6
    assert rows[-1]["platform"] == "其他 2 个平台"
    assert rows[-1]["count"] == 7
    assert rows[-1]["other_platform_count"] == 2


def test_platform_distribution_full_rows_keep_all_ten_platforms():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from src.ui.components.charts import PlatformDistributionChart

    data = {f"平台{i}": i for i in range(1, 11)}
    rows = PlatformDistributionChart.build_distribution_rows(data)
    collapsed = PlatformDistributionChart.build_collapsed_rows(data)

    assert len(rows) == 10
    assert len(collapsed) == 6
    assert collapsed[-1]["platform"] == "其他 5 个平台"
    assert collapsed[-1]["count"] == 15


def test_platform_distribution_methods_accept_empty_and_nonempty_data():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from src.ui.components.charts import PlatformDistributionChart

    chart = PlatformDistributionChart()
    chart.set_data({}, animate=False)
    assert chart.total_label.text() == "共 0 个账号"

    chart.set_data({"抖音": 3, "快手": 1}, animate=False)
    assert chart.total_label.text() == "共 4 个账号"
    assert "2 个平台" in chart.platform_count_label.text()

    chart.show_loading()
    assert chart.is_loading
    chart.reveal_platform_data({"抖音": 1}, animate_entry=False)


def test_platform_distribution_toggle_expanded_keeps_true_metrics():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from src.ui.components.charts import PlatformDistributionChart

    chart = PlatformDistributionChart()
    data = {f"平台{i}": i for i in range(1, 11)}
    chart.set_data(data, animate=False)

    assert chart.total_label.text() == "共 55 个账号"
    assert "10 个平台" in chart.platform_count_label.text()
    assert not chart.expand_button.isHidden()
    assert chart.expand_button.text() == "展开"
    assert len(chart._row_widgets) == 6

    chart._toggle_expanded()
    assert chart.expand_button.text() == "收起"
    assert len(chart._row_widgets) == 10

    chart._toggle_expanded()
    assert chart.expand_button.text() == "展开"
    assert len(chart._row_widgets) == 6


def test_workspace_chart_prefs_sane_defaults():
    assert CHART_OVERLAY_FADE_MS >= 100
    assert 200 <= CHART_ENTRY_ANIMATION_MS <= 600
