"""设置页「检查更新」按钮解析兼容测试"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QWidget

from src.ui.pages.settings_page import SettingsPage

pytestmark = pytest.mark.unit


class TestResolvePushSettingButton:
    def test_button_as_widget_attribute(self):
        widget = MagicMock(spec=QWidget)
        card = SimpleNamespace(button=widget)
        assert SettingsPage._resolve_push_setting_button(card) is widget

    def test_button_as_callable(self):
        widget = MagicMock(spec=QWidget)
        card = SimpleNamespace(button=lambda: widget)
        assert SettingsPage._resolve_push_setting_button(card) is widget

    def test_none_card(self):
        assert SettingsPage._resolve_push_setting_button(None) is None
