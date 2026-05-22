from PySide6.QtCore import Qt

from src.ui.pages.account.components.account_table_model import AccountTableModel
from src.ui.pages.publish.publish_record_table_model import PublishRecordTableModel


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
