"""Capture local diagnostic bundles when a publish step fails."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional

from src.infrastructure.browser.automation_api import Page

from src.infrastructure.common.path_manager import PathManager

logger = logging.getLogger(__name__)

_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(password|passwd|pwd|token|access[_-]?token|refresh[_-]?token|cookie|authorization|session|secret|api[_-]?key|csrf)"
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    (?P<prefix>["']?(?:password|passwd|pwd|token|access[_-]?token|refresh[_-]?token|cookie|authorization|session|secret|api[_-]?key|csrf)["']?\s*[:=]\s*)
    (?P<quote>["']?)
    (?P<value>[^"',;&<>\s]{6,})
    (?P=quote)
    """
)
_COOKIE_ATTR_RE = re.compile(r"(?i)(document\.cookie\s*=\s*['\"])[^'\"]+(['\"])")


@dataclass(frozen=True)
class PageDiagnosticsConfig:
    enabled: bool = True
    capture_html: bool = True
    capture_dom_summary: bool = True
    max_html_bytes: int = 5_000_000
    retention_days: int = 14


@dataclass(frozen=True)
class DiagnosticCaptureResult:
    path: str
    html_truncated: bool = False


def _safe_filename(value: str, default: str = "unknown", max_len: int = 80) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in (value or ""))
    safe = safe.strip("_")[:max_len]
    return safe or default


def _hash_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16] if text else ""


def redact_sensitive_text(text: str) -> str:
    if not text:
        return text
    redacted = _SENSITIVE_ASSIGNMENT_RE.sub(r"\g<prefix>\g<quote>***REDACTED***\g<quote>", text)
    return _COOKIE_ATTR_RE.sub(r"\1***REDACTED***\2", redacted)


def _redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if _SENSITIVE_KEY_RE.search(str(k)):
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact_json(v)
        return out
    if isinstance(value, list):
        return [_redact_json(v) for v in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def load_page_diagnostics_config() -> PageDiagnosticsConfig:
    try:
        from src.infrastructure.common.config.app_config_keys import (
            KEY_PUBLISH_DIAGNOSTICS,
            PUBLISH_DIAGNOSTICS_CAPTURE_DOM_SUMMARY,
            PUBLISH_DIAGNOSTICS_CAPTURE_HTML,
            PUBLISH_DIAGNOSTICS_ENABLED,
            PUBLISH_DIAGNOSTICS_MAX_HTML_BYTES,
            PUBLISH_DIAGNOSTICS_RETENTION_DAYS,
        )
        from src.infrastructure.common.config.app_config_merge import get_app_config_for_read

        root = get_app_config_for_read()
        raw = root.get(KEY_PUBLISH_DIAGNOSTICS) if isinstance(root, dict) else None
        data = raw if isinstance(raw, dict) else {}
        return PageDiagnosticsConfig(
            enabled=bool(data.get(PUBLISH_DIAGNOSTICS_ENABLED, True)),
            capture_html=bool(data.get(PUBLISH_DIAGNOSTICS_CAPTURE_HTML, True)),
            capture_dom_summary=bool(data.get(PUBLISH_DIAGNOSTICS_CAPTURE_DOM_SUMMARY, True)),
            max_html_bytes=max(1_000, int(data.get(PUBLISH_DIAGNOSTICS_MAX_HTML_BYTES, 5_000_000))),
            retention_days=max(1, int(data.get(PUBLISH_DIAGNOSTICS_RETENTION_DAYS, 14))),
        )
    except Exception:
        return PageDiagnosticsConfig()


# platform_id -> async capture extras(module_path attribute)
_PLATFORM_EXTRA_CAPTURE: dict[str, str] = {
    "xiaohongshu": "capture_xiaohongshu_extras",
}


class PageDomDiagnosticPlugin:
    """Create a self-contained local page diagnostic bundle."""

    def __init__(self, config: Optional[PageDiagnosticsConfig] = None) -> None:
        self.config = config or load_page_diagnostics_config()

    async def capture(
        self,
        page: Page,
        *,
        platform: str,
        step_name: str,
        reason: str,
        metadata: Optional[Mapping[str, Any]] = None,
        selector_probes: Optional[Mapping[str, Any]] = None,
    ) -> Optional[DiagnosticCaptureResult]:
        if not self.config.enabled:
            return None

        now = datetime.now()
        bundle_dir = self._create_bundle_dir(platform, step_name, reason, now)
        page_url = self._safe_page_attr(page, "url")
        page_title = await self._safe_title(page)
        html_truncated = False

        if self.config.capture_html:
            html_truncated = await self._write_html(page, bundle_dir / "page.html")

        dom_snapshot: dict[str, Any] = {}
        if self.config.capture_dom_summary:
            dom_snapshot = await self._capture_dom_snapshot(page)
        await self._write_json(bundle_dir / "dom_snapshot.json", dom_snapshot)

        probe_summary = await self._capture_selector_probes(page, selector_probes or {})
        await self._write_json(bundle_dir / "selector_probes.json", probe_summary)

        await self._capture_screenshot(page, bundle_dir / "screenshot.png")
        await self._write_jsonl(bundle_dir / "console.jsonl", self._extract_recent_console(metadata))
        await self._write_json(bundle_dir / "network_summary.json", self._extract_network_summary(metadata))

        diag_context = {}
        if isinstance(metadata, Mapping):
            raw_context = metadata.get("_diagnostic_context")
            if isinstance(raw_context, Mapping):
                diag_context = dict(raw_context)

        platform_extra = await self._run_platform_extras(
            platform,
            page,
            bundle_dir,
            metadata,
            step_name=step_name,
            reason=reason,
            page_url=page_url,
        )

        meta = {
            "platform": platform,
            "step_name": step_name,
            "reason": reason,
            "captured_at": now.isoformat(timespec="seconds"),
            "url": page_url,
            "title": page_title,
            "html_truncated": html_truncated,
            "account_name_hash": _hash_text(diag_context.get("account_name")),
            "file_name": Path(str(diag_context.get("file_path") or "")).name,
            "app_version": self._read_app_version(),
        }
        if diag_context.get("xhs_publish_snapshot"):
            meta["xhs_publish_snapshot"] = diag_context.get("xhs_publish_snapshot")
        if platform_extra:
            meta.update(platform_extra)
        await self._write_json(bundle_dir / "metadata.json", meta)

        logger.info("Saved publish diagnostic bundle: %s", bundle_dir)
        return DiagnosticCaptureResult(path=str(bundle_dir), html_truncated=html_truncated)

    def _create_bundle_dir(self, platform: str, step_name: str, reason: str, now: datetime) -> Path:
        platform_dir = PathManager.get_debug_diagnostics_dir(_safe_filename(platform))
        day_dir = platform_dir / now.strftime("%Y%m%d")
        bundle_name = (
            f"{now.strftime('%H%M%S_%f')[:13]}_"
            f"{_safe_filename(step_name, 'step', 30)}_"
            f"{_hash_text(reason)[:8]}"
        )
        bundle_dir = day_dir / bundle_name
        bundle_dir.mkdir(parents=True, exist_ok=True)
        return bundle_dir

    async def _write_html(self, page: Page, path: Path) -> bool:
        truncated = False
        try:
            html = redact_sensitive_text(await page.content())
            raw = html.encode("utf-8", errors="replace")
            if len(raw) > self.config.max_html_bytes:
                raw = raw[: self.config.max_html_bytes]
                truncated = True
            path.write_bytes(raw)
        except Exception as exc:
            await self._write_json(path.with_suffix(".error.json"), {"error": str(exc)})
        return truncated

    async def _capture_dom_snapshot(self, page: Page) -> dict[str, Any]:
        script = r"""
        () => {
            const MAX_ITEMS = 300;
            const MAX_TEXT = 300;
            const MAX_HTML = 800;
            const visible = (el) => {
                try {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 &&
                        style.display !== 'none' && style.visibility !== 'hidden';
                } catch (_) {
                    return false;
                }
            };
            const brief = (el, rootLabel) => {
                const rect = el.getBoundingClientRect();
                return {
                    root: rootLabel,
                    tag: el.tagName || '',
                    id: el.id || '',
                    className: String(el.className || '').slice(0, 300),
                    role: el.getAttribute('role') || '',
                    type: el.getAttribute('type') || '',
                    name: el.getAttribute('name') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    contenteditable: el.getAttribute('contenteditable') || '',
                    text: (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, MAX_TEXT),
                    rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
                    outerHTML: (el.outerHTML || '').slice(0, MAX_HTML),
                };
            };
            const selector = [
                'button','input','textarea','select','a','[contenteditable]',
                '[role="button"]','[role="textbox"]','[role="dialog"]','[role="alert"]',
                '[class*="upload" i]','[class*="publish" i]','[class*="post" i]',
                '[class*="form" i]','[class*="title" i]','[class*="desc" i]',
                '[class*="error" i]','[class*="modal" i]','[class*="dialog" i]'
            ].join(',');
            const roots = [{root: document, label: 'document'}];
            document.querySelectorAll('*').forEach((el, idx) => {
                if (el.shadowRoot) roots.push({root: el.shadowRoot, label: `shadow:${el.tagName}:${idx}`});
            });
            const elements = [];
            for (const {root, label} of roots) {
                let nodes = [];
                try { nodes = Array.from(root.querySelectorAll(selector)); } catch (_) { nodes = []; }
                for (const el of nodes) {
                    if (!visible(el)) continue;
                    elements.push(brief(el, label));
                    if (elements.length >= MAX_ITEMS) break;
                }
                if (elements.length >= MAX_ITEMS) break;
            }
            const frames = Array.from(document.querySelectorAll('iframe')).map((frame, index) => {
                try {
                    const doc = frame.contentDocument;
                    return {
                        index,
                        src: frame.src || '',
                        accessible: Boolean(doc),
                        title: doc ? doc.title : '',
                        bodyText: doc && doc.body ? doc.body.innerText.trim().replace(/\s+/g, ' ').slice(0, MAX_TEXT) : '',
                    };
                } catch (e) {
                    return {index, src: frame.src || '', accessible: false, error: String(e)};
                }
            });
            const xhsHosts = document.querySelectorAll('xhs-publish-btn').length;
            return {
                url: location.href,
                title: document.title,
                viewport: {w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio},
                readyState: document.readyState,
                activeElement: document.activeElement ? brief(document.activeElement, 'activeElement') : null,
                visibleInteractiveElements: elements,
                iframes: frames,
                xhsPublishHostCount: xhsHosts,
                closedShadowNote: xhsHosts > 0
                    ? 'xhs-publish-btn uses closed Shadow; inner buttons are in xhs_publish_snapshot.json when platform extras run.'
                    : '',
            };
        }
        """
        try:
            return _redact_json(await page.evaluate(script))
        except Exception as exc:
            return {"error": str(exc), "url": self._safe_page_attr(page, "url")}

    async def _run_platform_extras(
        self,
        platform: str,
        page: Page,
        bundle_dir: Path,
        metadata: Optional[Mapping[str, Any]],
        *,
        step_name: str,
        reason: str,
        page_url: str,
    ) -> dict[str, Any]:
        fn_name = _PLATFORM_EXTRA_CAPTURE.get((platform or "").strip().lower())
        if not fn_name:
            return {}
        try:
            if fn_name == "capture_xiaohongshu_extras":
                from src.plugins.pro.xiaohongshu.publish_failure_diagnostics import (
                    capture_xiaohongshu_extras,
                )

                return await capture_xiaohongshu_extras(
                    page,
                    bundle_dir,
                    metadata,
                    step_name=step_name,
                    reason=reason,
                    page_url=page_url,
                )
        except Exception as exc:
            logger.warning("platform diagnostic extras failed (%s): %s", platform, exc)
        return {}

    async def _capture_selector_probes(self, page: Page, probes: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, selector in list(probes.items())[:50]:
            selector_text = str(selector)
            item: dict[str, Any] = {"selector": selector_text, "count": 0, "visible": False}
            try:
                locator = page.locator(selector_text)
                count = await locator.count()
                item["count"] = count
                if count:
                    first = locator.first
                    item["visible"] = await first.is_visible()
                    try:
                        item["text"] = redact_sensitive_text((await first.inner_text(timeout=1000))[:300])
                    except Exception:
                        item["text"] = ""
                    try:
                        item["bounding_box"] = await first.bounding_box(timeout=1000)
                    except Exception:
                        item["bounding_box"] = None
            except Exception as exc:
                item["error"] = str(exc)
            out[str(key)] = item
        return out

    async def _capture_screenshot(self, page: Page, path: Path) -> None:
        try:
            await page.screenshot(path=str(path), full_page=True)
        except Exception as exc:
            await self._write_json(path.with_suffix(".error.json"), {"error": str(exc)})

    async def _write_json(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(_redact_json(data), ensure_ascii=False, indent=2), encoding="utf-8")

    async def _write_jsonl(self, path: Path, rows: Any) -> None:
        with path.open("w", encoding="utf-8") as fh:
            if isinstance(rows, list):
                for row in rows:
                    fh.write(json.dumps(_redact_json(row), ensure_ascii=False, separators=(",", ":")) + "\n")

    def _extract_recent_console(self, metadata: Optional[Mapping[str, Any]]) -> list[Any]:
        if not isinstance(metadata, Mapping):
            return []
        value = metadata.get("_diagnostic_console")
        return value if isinstance(value, list) else []

    def _extract_network_summary(self, metadata: Optional[Mapping[str, Any]]) -> dict[str, Any]:
        if not isinstance(metadata, Mapping):
            return {"failed_requests": [], "responses": []}
        value = metadata.get("_diagnostic_network")
        return value if isinstance(value, dict) else {"failed_requests": [], "responses": []}

    def _safe_page_attr(self, page: Page, attr: str) -> str:
        try:
            return str(getattr(page, attr, "") or "")
        except Exception:
            return ""

    async def _safe_title(self, page: Page) -> str:
        try:
            return await page.title()
        except Exception:
            return ""

    def _read_app_version(self) -> str:
        try:
            version_path = PathManager.get_resource_path("version.json")
            data = json.loads(version_path.read_text(encoding="utf-8"))
            return str(data.get("version") or "")
        except Exception:
            return ""
