from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.infrastructure.common.path_manager import PathManager
from src.plugins.core.diagnostics import PageDiagnosticsConfig, PageDomDiagnosticPlugin
from src.plugins.core.diagnostics.page_dom_diagnostic import redact_sensitive_text

pytestmark = pytest.mark.unit


class FakeLocator:
    @property
    def first(self):
        return self

    async def count(self):
        return 1

    async def is_visible(self):
        return True

    async def inner_text(self, timeout=None):
        return "发布按钮 token=secret-token-value"

    async def bounding_box(self, timeout=None):
        return {"x": 1, "y": 2, "width": 3, "height": 4}


class FakePage:
    url = "https://creator.example/upload"

    def __init__(self, html: str = "<html><body>ok</body></html>") -> None:
        self.html = html

    async def content(self):
        return self.html

    async def title(self):
        return "Creator"

    async def evaluate(self, script):
        return {
            "url": self.url,
            "title": "Creator",
            "visibleInteractiveElements": [
                {"tag": "BUTTON", "text": "发布", "outerHTML": "<button>发布</button>"}
            ],
        }

    async def screenshot(self, path: str, full_page: bool = True):
        Path(path).write_bytes(b"png")

    def locator(self, selector: str):
        return FakeLocator()


@pytest.fixture(autouse=True)
def reset_path_manager(tmp_path):
    PathManager._app_data_dir = tmp_path
    yield
    PathManager._app_data_dir = None


@pytest.mark.asyncio
async def test_capture_writes_diagnostic_bundle():
    plugin = PageDomDiagnosticPlugin(PageDiagnosticsConfig(max_html_bytes=100_000))

    result = await plugin.capture(
        FakePage('<html token="abc123456">password="super-secret"</html>'),
        platform="douyin",
        step_name="UploadMediaStep",
        reason="selector failed",
        metadata={
            "_diagnostic_context": {
                "account_name": "user-a",
                "file_path": "D:/videos/demo.mp4",
            }
        },
        selector_probes={"submit": "button.publish"},
    )

    assert result is not None
    bundle = Path(result.path)
    assert (bundle / "page.html").exists()
    assert (bundle / "screenshot.png").read_bytes() == b"png"
    assert (bundle / "console.jsonl").exists()
    assert (bundle / "network_summary.json").exists()

    metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["platform"] == "douyin"
    assert metadata["step_name"] == "UploadMediaStep"
    assert metadata["file_name"] == "demo.mp4"
    assert metadata["account_name_hash"]

    probes = json.loads((bundle / "selector_probes.json").read_text(encoding="utf-8"))
    assert probes["submit"]["count"] == 1
    assert "***REDACTED***" in probes["submit"]["text"]


@pytest.mark.asyncio
async def test_capture_truncates_large_html():
    plugin = PageDomDiagnosticPlugin(PageDiagnosticsConfig(max_html_bytes=20))

    result = await plugin.capture(
        FakePage("<html>" + "x" * 100 + "</html>"),
        platform="kuaishou",
        step_name="Step",
        reason="large",
    )

    assert result is not None
    bundle = Path(result.path)
    assert result.html_truncated is True
    assert (bundle / "page.html").stat().st_size == 20
    metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["html_truncated"] is True


def test_redact_sensitive_text_masks_common_assignments():
    text = 'token="abcdef123456"; password: "secret123"; document.cookie="sid=abc"'

    redacted = redact_sensitive_text(text)

    assert "abcdef123456" not in redacted
    assert "secret123" not in redacted
    assert "sid=abc" not in redacted
    assert redacted.count("***REDACTED***") >= 3
