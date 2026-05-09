import pytest


from src.ui.publish.work_description import (
    LibraryFetchCoordinator,
    PublishDescriptionState,
)


class TestLibraryFetchCoordinator:
    def test_single_select(self):
        c = LibraryFetchCoordinator()
        assert c.update_pending(title=True, desc=False) is True
        item, title, desc = c.complete({"short_title": "t", "description": "d"})
        assert item is not None
        assert title is True
        assert desc is False

    def test_double_select_dedupes(self):
        c = LibraryFetchCoordinator()
        assert c.update_pending(title=True, desc=False) is True
        assert c.update_pending(title=True, desc=True) is False
        item, title, desc = c.complete({"short_title": "t", "description": "d"})
        assert item is not None
        assert title is True
        assert desc is True

    def test_uncheck_cancels_pending(self):
        c = LibraryFetchCoordinator()
        assert c.update_pending(title=True, desc=True) is True
        assert c.update_pending(title=False, desc=False) is False
        item, title, desc = c.complete({"short_title": "t", "description": "d"})
        assert item is not None
        assert title is False
        assert desc is False


class TestPublishDescriptionState:
    def test_single_select_and_uncheck_restore(self):
        s = PublishDescriptionState(title="手动标题", desc="手动简介")
        s.toggle_use_library_title(True, "库标题")
        assert s.title == "库标题"
        assert s.manual_title_backup == "手动标题"
        s.toggle_use_library_title(False, "库标题")
        assert s.title == "手动标题"

    def test_double_select(self):
        s = PublishDescriptionState(title="T0", desc="D0")
        s.toggle_use_library_title(True, "T1")
        s.toggle_use_library_desc(True, "D1")
        assert s.title == "T1"
        assert s.desc == "D1"

    def test_manual_edit_does_not_overwrite_backup(self):
        s = PublishDescriptionState(title="T0", desc="D0")
        s.toggle_use_library_title(True, "T_lib")
        s.on_title_edited("T_user_override")
        assert s.manual_title_backup == "T0"
        s.toggle_use_library_title(False, "T_lib")
        assert s.title == "T0"

    def test_restore_library_without_repeat_backup(self):
        s = PublishDescriptionState(title="T0", desc="D0")
        s.toggle_use_library_title(True, "T_lib")
        s.on_title_edited("T_user_override")
        s.toggle_use_library_title(False, "T_lib")
        assert s.title == "T0"
        s.toggle_use_library_title(True, "T_lib")
        assert s.title == "T_lib"

    def test_state_roundtrip(self):
        s = PublishDescriptionState(
            title="t",
            desc="d",
            apply_to_all_tasks=False,
            use_library_title=True,
            use_library_desc=True,
            manual_title_backup="t0",
            manual_desc_backup="d0",
            auto_match_enabled=True,
            match_mode="random_category",
            random_category_id=12,
            copywriting_assign_strategy="random",
        )
        s2 = PublishDescriptionState.from_dict(s.to_dict())
        assert s2.to_dict() == s.to_dict()
