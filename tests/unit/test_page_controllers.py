from __future__ import annotations

from types import SimpleNamespace

from src.pro_features.batch.pages.batch_task_creation_controller import (
    BatchTaskCreationController,
    BatchTaskCreationState,
)
from src.ui.pages.account.account_page_controller import AccountPageController
from src.ui.pages.material.media_library_page_controller import MediaLibraryPageController
from src.ui.pages.publish.publish_records_controller import PublishRecordsController
from src.ui.pages.publish.single_task_creation_controller import (
    SingleTaskCreationController,
    SingleTaskFormState,
)


def test_single_task_form_state_reads_page_snapshot():
    page = SimpleNamespace(
        _media_mode="image",
        selected_file_path="D:/media/a",
        selected_account={"type": "group"},
        editing_record_id=12,
        _file_from_auto_library=True,
    )

    state = SingleTaskFormState.from_page(page)

    assert state.media_mode == "image"
    assert state.selected_file_path == "D:/media/a"
    assert state.selected_account_type == "group"
    assert state.editing_record_id == 12
    assert state.is_auto_library_file is True


def test_single_task_controller_delegates_publish_to_legacy_method():
    called = []
    page = SimpleNamespace(
        _media_mode="video",
        selected_file_path="",
        selected_account=None,
        editing_record_id=None,
        _on_publish_legacy=lambda: called.append("publish"),
    )

    SingleTaskCreationController(page).publish()

    assert called == ["publish"]


def test_batch_state_reads_counts_and_matching_flags():
    page = SimpleNamespace(
        selected_accounts=[{"id": 1}, {"id": 2}],
        video_list=[{"file_path": "a.mp4"}],
        time_slots=["2026-05-22 10:00"],
        auto_match_enabled=True,
        match_mode="strict",
    )

    state = BatchTaskCreationState.from_page(page)

    assert state.selected_account_count == 2
    assert state.video_count == 1
    assert state.time_slot_count == 1
    assert state.auto_match_enabled is True
    assert state.match_mode == "strict"


def test_batch_controller_delegates_import_actions():
    called = []
    page = SimpleNamespace(
        selected_accounts=[],
        video_list=[],
        time_slots=[],
        _on_import_files_legacy=lambda: called.append("files"),
        _on_import_folder_legacy=lambda: called.append("folder"),
        _on_choose_from_library_legacy=lambda: called.append("library"),
    )
    controller = BatchTaskCreationController(page)

    controller.import_files()
    controller.import_folder()
    controller.choose_from_library()

    assert called == ["files", "folder", "library"]


def test_publish_records_controller_delegates_load_more():
    called = []
    page = SimpleNamespace(
        publish_records=[{"id": 1}],
        _total_record_count=2,
        _has_more_records=True,
        _loading_more_records=False,
        _load_more_publish_records=lambda: called.append("load_more"),
    )

    controller = PublishRecordsController(page)
    controller.load_more()

    assert called == ["load_more"]
    assert controller.state.loaded_count == 1
    assert controller.state.has_more is True


def test_account_controller_delegates_refresh():
    called = []
    page = SimpleNamespace(
        accounts=[{"id": 1}],
        _accounts_data_stale=True,
        _account_page_first_show=False,
        _on_refresh_legacy=lambda *, silent=False: called.append(silent),
    )

    controller = AccountPageController(page)
    controller.refresh(silent=True)

    assert called == [True]
    assert controller.state.account_count == 1
    assert controller.state.stale is True


def test_media_library_controller_filters_owner_status_and_owner():
    items = [
        SimpleNamespace(owner="未分配"),
        SimpleNamespace(owner="账号A"),
        SimpleNamespace(owner="账号B"),
    ]
    controller = MediaLibraryPageController(SimpleNamespace())

    assert controller.filter_items(items, owner_status="未分配", owner="全部账号") == [
        items[0]
    ]
    assert controller.filter_items(items, owner_status="已分配", owner="账号A") == [
        items[1]
    ]
    assert controller.state.total_count == 3
    assert controller.state.visible_count == 1
