"""账号统计概览卡"""

import pytest
from PySide6.QtWidgets import QApplication

from src.ui.components.account_platform_overview_card import (
    AccountPlatformOverviewCard,
    PlatformDistributionBarRow,
    PlatformStackedBar,
    build_overview_platform_rows,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_build_overview_platform_rows_collapses_extra(qapp):
    data = {f"平台{i}": i + 1 for i in range(6)}
    rows = build_overview_platform_rows(data)
    assert len(rows) == 5
    assert rows[-1].get("is_other") is True


def test_overview_card_reveal_shows_bars_not_tiles(qapp):
    card = AccountPlatformOverviewCard(half_column=True)
    try:
        card.show_loading()
        account = {
            "total": 18,
            "online": 18,
            "offline": 0,
            "by_platform": {"douyin": 10, "wechat_video": 6, "xiaohongshu": 1, "kuaishou": 1},
        }
        platform_cn = {"抖音": 10, "视频号": 6, "小红书": 1, "快手": 1}
        card.reveal(account, platform_cn, animate=False)
        assert card._title_label.text() == "账号统计"
        assert card._total_label.text() == "18"
        assert "18 在线" in card._online_badge.text()
        assert "4 个平台" in card._platform_hint_label.text()
        bar_rows = [w for w in card._bar_widgets if isinstance(w, PlatformDistributionBarRow)]
        assert len(bar_rows) == 4
        assert any(isinstance(w, PlatformStackedBar) for w in card._bar_widgets)
        assert not card.is_loading
        style = card.styleSheet() or ""
        assert "border-left" not in style
    finally:
        card.deleteLater()
        qapp.processEvents()
