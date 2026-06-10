from __future__ import annotations

import pytest

from src.ui.account import add_account_dialog as add_dialog_module
from src.ui.account.add_account_dialog import AddAccountDialog


pytestmark = pytest.mark.unit


def test_skip_fingerprint_config_for_all_platforms() -> None:
    dialog = AddAccountDialog()

    assert dialog._should_skip_fingerprint_config("xiaohongshu") is True
    assert dialog._should_skip_fingerprint_config("douyin") is True


def test_add_xhs_account_skips_fingerprint_dialog(monkeypatch) -> None:
    class FakePlatformSelectMessageBox:
        selected_platform = "xiaohongshu"

        def __init__(self, parent=None) -> None:
            pass

        def exec(self) -> bool:
            return True

    monkeypatch.setattr(add_dialog_module, "FLUENT_WIDGETS_AVAILABLE", True)
    monkeypatch.setattr(add_dialog_module, "PlatformSelectMessageBox", FakePlatformSelectMessageBox)
    monkeypatch.setattr(
        add_dialog_module.AddAccountDialog,
        "_should_skip_fingerprint_config",
        lambda self, platform_id: True,
    )

    result = AddAccountDialog().show()

    assert result is not None
    assert result["platform"] == "xiaohongshu"
    assert result["fingerprint_config"] is None


def test_add_non_xhs_account_skips_fingerprint_dialog(monkeypatch) -> None:
    class FakePlatformSelectMessageBox:
        selected_platform = "douyin"

        def __init__(self, parent=None) -> None:
            pass

        def exec(self) -> bool:
            return True

    monkeypatch.setattr(add_dialog_module, "FLUENT_WIDGETS_AVAILABLE", True)
    monkeypatch.setattr(add_dialog_module, "PlatformSelectMessageBox", FakePlatformSelectMessageBox)

    result = AddAccountDialog().show()

    assert result is not None
    assert result["platform"] == "douyin"
    assert result["fingerprint_config"] is None
