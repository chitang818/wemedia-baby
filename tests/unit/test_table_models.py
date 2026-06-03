from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.ui.pages.account.components.account_table_model import AccountTableModel
from src.ui.pages.publish.publish_record_table_model import PublishRecordTableModel
from src.ui.pages.publish.publish_record_table_view import PublishRecordTableView
from src.utils.platform_names import get_platform_display_name
from src.ui.pages.publish.publish_records_page import PublishRecordsPage
from src.ui.pages.publish.publish_recycle_bin_page import PublishRecycleBinPage


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_account_table_model_indexes_records_by_account_id() -> None:
    model = AccountTableModel()
    model.set_records(
        [
            {"id": 1, "platform": "douyin", "platform_username": "Alice", "login_status": "online"},
            {"id": 2, "platform": "kuaishou", "platform_username": "Bob", "login_status": "offline"},
        ]
    )

    assert model.rowCount() == 2
    assert model.columnCount() == len(AccountTableModel.HEADERS)
    assert model.row_for_account_id(2) == 1
    assert model.data(model.index(0, AccountTableModel.COL_USERNAME)) == "Alice"
    assert model.data(model.index(0, AccountTableModel.COL_LOGIN_STATUS)) == "在线"
    assert model.data(model.index(0, AccountTableModel.COL_USERNAME), AccountTableModel.AccountIdRole) == 1


def test_publish_record_table_model_indexes_records_by_id() -> None:
    model = PublishRecordTableModel()
    model.set_records(
        [
            {"id": 10, "platform": "douyin", "platform_username": "Alice", "status": "pending"},
            {"id": 11, "file_type": "image", "platform": "kuaishou", "status": "success"},
        ]
    )

    assert model.rowCount() == 2
    assert model.columnCount() == len(PublishRecordTableModel.HEADERS)
    assert model.row_for_record_id(11) == 1
    assert model.data(model.index(1, 1)) == "图文"
    assert model.data(model.index(0, PublishRecordTableModel.COL_STATUS)) == "⏳ 待发布"
    assert model.data(model.index(0, 0), Qt.ItemDataRole.TextAlignmentRole)


def test_publish_record_table_model_supports_cell_overrides_and_remove() -> None:
    model = PublishRecordTableModel()
    model.set_records(
        [
            {"id": 10, "platform": "douyin", "status": "pending"},
            {"id": 11, "platform": "kuaishou", "status": "success"},
        ]
    )

    assert model.set_cell_text(10, PublishRecordTableModel.COL_STATUS, "publishing")
    assert model.data(model.index(0, PublishRecordTableModel.COL_STATUS)) == "publishing"
    assert model.remove_record_at(0)
    assert model.rowCount() == 1
    assert model.row_for_record_id(11) == 0


def test_publish_record_table_model_recycle_page_columns() -> None:
    model = PublishRecordTableModel()
    model.set_recycle_page(True)
    model.set_action_text("查看")
    model.set_records(
        [
            {
                "id": 20,
                "platform": "douyin",
                "status": "deleted_success",
                "file_path": r"D:\media\demo.mp4",
                "title": "demo",
            }
        ]
    )

    assert model.headerData(PublishRecordTableModel.COL_SCHEDULED_TIME, Qt.Orientation.Horizontal) == "发布时间"
    assert model.headerData(PublishRecordTableModel.COL_FILE_LOCATION, Qt.Orientation.Horizontal) == "来源"
    assert model.data(model.index(0, PublishRecordTableModel.COL_LOCATION)) == "回收（原已发布）"
    assert model.data(model.index(0, PublishRecordTableModel.COL_FILE_LOCATION)) == "已发布"
    assert model.data(model.index(0, PublishRecordTableModel.COL_ACTION)) == "查看"


def test_publish_records_navigation_refresh_skips_fresh_page() -> None:
    _qapp()
    page = PublishRecordsPage.__new__(PublishRecordsPage)
    page._content_initialized = True
    page.records_table = object()
    page._data_stale = False
    page._last_filter_render_state = ("fresh",)
    calls = {"load": 0, "filter": 0}
    page._load_publish_records = lambda: calls.__setitem__("load", calls["load"] + 1)
    page._apply_filters = lambda: calls.__setitem__("filter", calls["filter"] + 1)

    page.refresh_after_navigation()

    assert calls == {"load": 0, "filter": 0}


def test_publish_records_navigation_refresh_loads_stale_page() -> None:
    _qapp()
    page = PublishRecordsPage.__new__(PublishRecordsPage)
    page._content_initialized = True
    page.records_table = object()
    page._data_stale = True
    page._last_filter_render_state = ("old",)
    calls = {"load": 0, "filter": 0}
    page._load_publish_records = lambda: calls.__setitem__("load", calls["load"] + 1)
    page._apply_filters = lambda: calls.__setitem__("filter", calls["filter"] + 1)

    page.refresh_after_navigation()

    assert calls == {"load": 1, "filter": 0}


def test_recycle_navigation_refresh_skips_fresh_page() -> None:
    _qapp()
    page = PublishRecycleBinPage.__new__(PublishRecycleBinPage)
    page._content_initialized = True
    page.records_table = object()
    page._data_stale = False
    page.deleted_records = [{"id": 1}]
    page._total_deleted_count = 1
    calls = {"load": 0}
    page._load_deleted_records = lambda: calls.__setitem__("load", calls["load"] + 1)

    page.refresh_after_navigation()

    assert calls == {"load": 0}


def test_publish_record_table_platform_column_fits_display_names() -> None:
    _qapp()
    table = PublishRecordTableView()
    col = PublishRecordTableModel.COL_PLATFORM
    width = table.columnWidth(col)
    fm = PublishRecordTableView._table_font_metrics()
    for platform_id in ("xiaohongshu", "douyin", "duoduoshipin", "bilibili"):
        label = get_platform_display_name(platform_id)
        assert fm.horizontalAdvance(label) + 16 <= width


def test_publish_record_table_view_default_visual_order_is_unchanged() -> None:
    _qapp()
    table = PublishRecordTableView()
    header = table.horizontalHeader()

    assert header.visualIndex(PublishRecordTableModel.COL_STATUS) == PublishRecordTableModel.COL_STATUS
    assert header.visualIndex(PublishRecordTableModel.COL_ACTION) == PublishRecordTableModel.COL_ACTION
    assert header.visualIndex(PublishRecordTableModel.COL_SCHEDULED_TIME) == PublishRecordTableModel.COL_SCHEDULED_TIME


def test_publish_record_table_view_pending_order_moves_status_and_action_before_publish_time() -> None:
    _qapp()
    table = PublishRecordTableView(pending_column_order=True)
    header = table.horizontalHeader()
    m = PublishRecordTableModel

    assert header.logicalIndex(10) == m.COL_STATUS
    assert header.logicalIndex(11) == m.COL_ACTION
    assert header.logicalIndex(12) == m.COL_SCHEDULED_TIME
    assert header.visualIndex(m.COL_DESCRIPTION) < header.visualIndex(m.COL_STATUS)
    assert header.visualIndex(m.COL_ACTION) < header.visualIndex(m.COL_SCHEDULED_TIME)


def test_publish_record_table_view_pending_order_keeps_logical_column_mapping() -> None:
    _qapp()
    table = PublishRecordTableView(pending_column_order=True)
    table.set_records([{"id": 10, "platform": "douyin", "status": "pending"}])

    assert table.item(0, PublishRecordTableModel.COL_STATUS).text() == "⏳ 待发布"
    assert table.item(0, PublishRecordTableModel.COL_ACTION).text() == "编辑"
    assert table.item(0, PublishRecordTableModel.COL_ACTION).data(Qt.ItemDataRole.UserRole) == 10


def test_publish_record_table_view_recycle_mode_is_idempotent(monkeypatch) -> None:
    _qapp()
    calls = {"apply": 0}
    original = PublishRecordTableView._apply_legacy_table_visual_defaults

    def counted_apply(self) -> None:
        calls["apply"] += 1
        original(self)

    monkeypatch.setattr(PublishRecordTableView, "_apply_legacy_table_visual_defaults", counted_apply)
    table = PublishRecordTableView(recycle_page=True)
    initial_calls = calls["apply"]

    table.set_recycle_page(True)

    assert calls["apply"] == initial_calls
