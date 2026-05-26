from pathlib import Path

from src.ui.dialogs.publish_diagnostic_dialog import format_elided_diagnostic_path
from src.ui.pages.publish.publish_list_page import PublishListPage


class _FakeLogWidget:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def append_warning(self, message: str) -> None:
        self.warnings.append(message)


def _make_page() -> PublishListPage:
    page = PublishListPage.__new__(PublishListPage)
    page._shown_diagnostic_paths = set()
    page._diagnostic_dialogs = []
    page._pending_publish_failure_notice = None
    page.window = lambda: None
    page.isVisible = lambda: True
    return page


def test_publish_diagnostic_ready_appends_log_and_shows_dialog_once() -> None:
    page = _make_page()
    page.log_widget = _FakeLogWidget()
    dialogs: list[tuple[str, str | None]] = []

    def _capture(path: str, *, error_message: str | None = None, platform: str = "") -> None:
        dialogs.append((path, error_message))

    page._show_diagnostic_dialog = _capture

    page._handle_publish_diagnostic_ready(
        r"C:\debug\diagnostics\case1",
        error_message="发布后未能确认成功",
    )
    page._handle_publish_diagnostic_ready(
        r"C:\debug\diagnostics\case1",
        error_message="发布后未能确认成功",
    )

    assert len(page.log_widget.warnings) == 1
    assert "已保存失败诊断包" in page.log_widget.warnings[0]
    assert r"C:\debug\diagnostics\case1" not in page.log_widget.warnings[0]
    assert dialogs == [(r"C:\debug\diagnostics\case1", "发布后未能确认成功")]


def test_publish_diagnostic_ready_ignores_empty_path() -> None:
    page = _make_page()
    page.log_widget = _FakeLogWidget()
    dialogs: list[tuple[str, str | None]] = []

    def _capture(path: str, *, error_message: str | None = None, platform: str = "") -> None:
        dialogs.append((path, error_message))

    page._show_diagnostic_dialog = _capture

    page._handle_publish_diagnostic_ready("   ")

    assert page.log_widget.warnings == []
    assert dialogs == []


def test_enqueue_publish_failure_notice_flushes_on_visible_page(monkeypatch) -> None:
    page = _make_page()
    presented: list[dict] = []

    def _present(
        error_message: str,
        diagnostic_path: str,
        task_id: object = None,
        platform: str = "",
    ) -> None:
        presented.append(
            {
                "error_message": error_message,
                "diagnostic_path": diagnostic_path,
                "task_id": task_id,
                "platform": platform,
            }
        )

    page._present_publish_failure_notice = _present
    page._schedule_base_page_timer = lambda _name, _ms, fn: fn()

    page._enqueue_publish_failure_notice(
        error_message="SubmitStep 失败",
        diagnostic_path=r"C:\debug\case2",
        task_id=679,
    )

    assert presented == [
        {
            "error_message": "SubmitStep 失败",
            "diagnostic_path": r"C:\debug\case2",
            "task_id": 679,
            "platform": "",
        }
    ]


def test_enqueue_publish_failure_notice_defers_when_page_hidden() -> None:
    page = _make_page()
    page.isVisible = lambda: False
    page._schedule_base_page_timer = lambda *_args: None

    page._enqueue_publish_failure_notice(
        error_message="失败",
        diagnostic_path="",
        task_id=1,
    )

    assert page._pending_publish_failure_notice is not None
    assert page._pending_publish_failure_notice["error_message"] == "失败"


def test_open_diagnostic_folder_opens_existing_directory(monkeypatch, tmp_path: Path) -> None:
    page = _make_page()
    opened_urls = []

    monkeypatch.setattr(
        "src.ui.pages.publish.publish_list_page.QDesktopServices.openUrl",
        lambda url: opened_urls.append(url.toLocalFile()) or True,
    )

    page._open_diagnostic_folder(str(tmp_path))

    assert len(opened_urls) == 1
    assert Path(opened_urls[0]) == tmp_path


def test_open_diagnostic_folder_warns_for_missing_directory(monkeypatch, tmp_path: Path) -> None:
    page = _make_page()
    warnings = []

    monkeypatch.setattr(
        "src.ui.pages.publish.publish_list_page.InfoBar.warning",
        lambda title, content, **kwargs: warnings.append((title, content)),
    )
    monkeypatch.setattr(
        "src.ui.pages.publish.publish_list_page.QDesktopServices.openUrl",
        lambda url: (_ for _ in ()).throw(AssertionError("openUrl should not be called")),
    )

    page._open_diagnostic_folder(str(tmp_path / "missing"))

    assert warnings
    assert warnings[0][0] == "无法打开诊断目录"


def test_format_elided_diagnostic_path_uses_tail_segments() -> None:
    path = r"C:\Users\demo\AppData\Local\WeMediaBaby\debug\diagnostics\xiaohongshu\20260525\194538_SubmitStep_ab12cd34"
    display = format_elided_diagnostic_path(path)

    assert display.startswith("…\\")
    assert "xiaohongshu" in display
    assert "20260525" in display
    assert "194538_SubmitStep_ab12cd34" in display
    assert r"C:\Users" not in display
