from src.ui.main_window import get_startup_preload_page_names
from src.infrastructure.common.startup_prefs import (
    normalize_startup_preload_mode,
    resolve_startup_preload_mode,
    startup_preload_timing,
)


def test_startup_preload_mode_defaults_to_off(monkeypatch):
    monkeypatch.delenv("WEMEDIABABY_STARTUP_PRELOADS", raising=False)
    assert resolve_startup_preload_mode() == "off"


def test_startup_preload_timing_defaults_to_8s_base(monkeypatch):
    monkeypatch.delenv("WEMEDIABABY_STARTUP_PRELOAD_BASE_MS", raising=False)
    base_ms, step_ms = startup_preload_timing()
    assert base_ms == 8000
    assert step_ms == 500


def test_normalize_startup_preload_mode_aliases():
    assert normalize_startup_preload_mode("false") == "off"
    assert normalize_startup_preload_mode("minimal") == "minimal"
    assert normalize_startup_preload_mode("all") == "full"


def test_startup_preloads_default_to_minimal_pages():
    assert get_startup_preload_page_names(mode="minimal") == [
        "publish_list_page",
        "account_page",
        "single_task_creation_page",
    ]


def test_startup_preloads_can_be_disabled():
    assert get_startup_preload_page_names(mode="false") == []


def test_startup_preloads_full_mode_matches_legacy_page_set():
    assert get_startup_preload_page_names(
        mode="true",
        batch_feature_available=True,
    ) == [
        "publish_list_page",
        "account_page",
        "single_task_creation_page",
        "publish_records_page",
        "settings_page",
        "batch_task_creation_page",
    ]
