from src.ui.page_factory import _REGISTRY


def test_single_task_creation_page_uses_direct_module_import():
    assert _REGISTRY["single_task_creation_page"] == (
        "src.ui.pages.publish.single_task_creation_page",
        "SingleTaskCreationPage",
    )


def test_single_task_creation_page_uses_light_work_description_import():
    source = "src/ui/pages/publish/single_task_creation_page.py"
    with open(source, "r", encoding="utf-8") as f:
        text = f.read()

    assert "from src.ui.publish.work_description import WorkDescriptionEditController" not in text
    assert "publish_description_dialog import" not in text
    assert "work_declaration_prefs import" not in text


def test_single_task_creation_preview_init_is_not_scheduled_at_150ms():
    source = "src/ui/pages/publish/single_task_creation_page.py"
    with open(source, "r", encoding="utf-8") as f:
        text = f.read()

    assert "preview_video_widget_idle_init" in text
    assert "150,\n                self._ensure_preview_video_widget" not in text


def test_single_task_creation_page_uses_more_publish_settings_card():
    source = "src/ui/pages/publish/single_task_creation_page.py"
    with open(source, "r", encoding="utf-8") as f:
        text = f.read()

    assert "MorePublishSettingsCard" in text
    assert "_more_publish_settings_card" in text
    assert "build_publish_extension_payload" in text
    assert "apply_from_publish_record" in text
    assert "_refresh_more_publish_settings_ui" in text
    assert "_refresh_account_dependent_settings_ui" in text
    assert "_create_publish_options_card" not in text
    assert "_publish_opts_stack" not in text


def test_single_task_creation_page_uses_merged_publish_cards():
    source = "src/ui/pages/publish/single_task_creation_page.py"
    with open(source, "r", encoding="utf-8") as f:
        text = f.read()

    assert "_create_schedule_card" in text
    assert "_create_extended_info_card" not in text
    assert "extended_info_card = self._create_extended_info_card()" not in text
    assert "schedule_card = self._create_schedule_card()" in text
