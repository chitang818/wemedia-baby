from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.ui.pages.material.media_library_table_model import MediaLibraryTableModel
from src.ui.pages.material.media_library_table_view import MediaLibraryTableView


def test_media_library_table_model_video_display_and_update_signal() -> None:
    model = MediaLibraryTableModel(MediaLibraryTableModel.KIND_VIDEO)
    item = SimpleNamespace(
        path=r"D:\media\a.mp4",
        name="a.mp4",
        size_mb=12.345,
        duration="-",
        resolution="-",
        orientation="-",
        owner="未分配",
        in_use=False,
    )
    model.set_items([item])

    assert model.rowCount() == 1
    assert model.columnCount() == len(MediaLibraryTableModel.VIDEO_HEADERS)
    assert model.data(model.index(0, MediaLibraryTableModel.COL_NO)) == "1"
    assert model.data(model.index(0, MediaLibraryTableModel.COL_NAME)) == "a.mp4"
    assert model.data(model.index(0, MediaLibraryTableModel.COL_VIDEO_SIZE)) == "12.35 MB"
    assert model.data(model.index(0, MediaLibraryTableModel.COL_VIDEO_OWNER)) == "未分配"
    assert model.data(model.index(0, MediaLibraryTableModel.COL_VIDEO_USAGE)) == ""
    assert model.data(model.index(0, 0), MediaLibraryTableModel.RawItemRole) is item

    changed = []
    model.dataChanged.connect(lambda top, bottom, roles: changed.append((top.column(), bottom.column(), roles)))
    item.in_use = True
    assert model.notify_item_changed(item.path, [MediaLibraryTableModel.COL_VIDEO_USAGE])
    assert changed[-1][0] == MediaLibraryTableModel.COL_VIDEO_USAGE
    assert changed[-1][1] == MediaLibraryTableModel.COL_VIDEO_USAGE
    assert model.data(model.index(0, MediaLibraryTableModel.COL_VIDEO_USAGE)) == "已占用"


def test_media_library_table_model_image_folder_display() -> None:
    model = MediaLibraryTableModel(MediaLibraryTableModel.KIND_IMAGE_FOLDER)
    item = SimpleNamespace(
        path=r"D:\media\images\set-a",
        name="set-a",
        image_count=8,
        size_mb=3.2,
        owner="账号A",
        in_use=True,
    )
    model.set_items([item])

    assert model.rowCount() == 1
    assert model.columnCount() == len(MediaLibraryTableModel.IMAGE_HEADERS)
    assert model.headerData(MediaLibraryTableModel.COL_IMAGE_COUNT, Qt.Orientation.Horizontal) == "图片数量"
    assert model.data(model.index(0, MediaLibraryTableModel.COL_NAME)) == "set-a"
    assert model.data(model.index(0, MediaLibraryTableModel.COL_IMAGE_COUNT)) == "8"
    assert model.data(model.index(0, MediaLibraryTableModel.COL_IMAGE_SIZE)) == "3.20 MB"
    assert model.data(model.index(0, MediaLibraryTableModel.COL_IMAGE_OWNER)) == "账号A"
    assert model.data(model.index(0, MediaLibraryTableModel.COL_IMAGE_USAGE)) == "已占用"


def test_media_library_table_view_item_adapter_and_selection() -> None:
    app = QApplication.instance() or QApplication([])
    table = MediaLibraryTableView(kind=MediaLibraryTableModel.KIND_VIDEO)
    item = SimpleNamespace(
        path=r"D:\media\a.mp4",
        name="a.mp4",
        size_mb=1.0,
        duration="00:00:10",
        resolution="1080x1920",
        orientation="竖屏",
        owner="账号A",
        in_use=False,
    )
    table.set_items([item])
    table.selectRow(0)

    adapter = table.item(0, MediaLibraryTableModel.COL_NO)
    assert adapter is not None
    assert adapter.data(Qt.ItemDataRole.UserRole) is item
    assert table.item(0, MediaLibraryTableModel.COL_NAME).text() == "a.mp4"
    assert [selected.data(Qt.ItemDataRole.UserRole) for selected in table.selectedItems()] == [item]

    table.removeRow(0)
    assert table.rowCount() == 0
    table.deleteLater()
    assert app is not None
