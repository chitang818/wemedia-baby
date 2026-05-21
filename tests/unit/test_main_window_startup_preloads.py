from src.ui.main_window import get_startup_preload_page_names


def test_startup_preloads_default_to_minimal_pages():
    assert get_startup_preload_page_names(mode="minimal") == [
        "publish_list_page",
        "account_page",
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
        "publish_records_page",
        "single_task_creation_page",
        "settings_page",
        "batch_task_creation_page",
    ]
