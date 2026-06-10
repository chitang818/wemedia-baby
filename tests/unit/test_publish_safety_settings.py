from __future__ import annotations

import pytest

from src.ui.pages.publish import list_settings_dialog as settings


pytestmark = pytest.mark.unit


def test_effective_publish_interval_respects_platform_minimum(monkeypatch) -> None:
    monkeypatch.setattr(settings, "_publish_list_dict", lambda: {"interval_seconds": 20})
    monkeypatch.setattr(settings, "should_respect_platform_publish_interval", lambda: True)

    assert settings.get_effective_publish_interval_seconds("douyin") >= 60


def test_publish_browser_is_forced_visible(monkeypatch) -> None:
    monkeypatch.setattr(settings, "_publish_list_dict", lambda: {"show_browser": False})
    monkeypatch.setattr(settings, "should_force_visible_publish_browser", lambda: True)

    assert settings.get_publish_show_browser() is True


def test_publish_interval_sampling_returns_configured_value() -> None:
    assert settings.sample_publish_interval_delay_seconds(20) == 20.0


def test_extreme_speed_option_is_not_exposed() -> None:
    labels = [label for label, _rate in settings.SPEED_OPTIONS]

    assert "极速" not in labels
