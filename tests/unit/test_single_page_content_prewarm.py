from src.ui.main_window import MainWindow


def test_single_page_content_prewarm_enabled_by_default(monkeypatch):
    monkeypatch.delenv("WEMEDIABABY_SINGLE_PAGE_CONTENT_PREWARM", raising=False)
    window = MainWindow.__new__(MainWindow)

    assert MainWindow._single_page_content_prewarm_enabled(window) is True


def test_single_page_content_prewarm_can_be_disabled(monkeypatch):
    monkeypatch.setenv("WEMEDIABABY_SINGLE_PAGE_CONTENT_PREWARM", "0")
    window = MainWindow.__new__(MainWindow)

    assert MainWindow._single_page_content_prewarm_enabled(window) is False
