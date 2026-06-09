# -*- coding: utf-8 -*-
"""Read-only Xiaohongshu browser-environment diagnostics.

The snapshot is intentionally defensive: it records observable browser state and
cookie names, never cookie values or authorization headers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Mapping, Optional

from src.infrastructure.browser.automation_api import Page


RISK_PROMPT_KEYWORDS: tuple[str, ...] = (
    "操作频繁",
    "风控",
    "异常验证",
    "安全验证",
    "验证失败",
    "环境异常",
    "风险",
    "稍后重试",
    "脚本",
    "自动化",
    "自动化软件",
    "AI",
    "人工智能",
    "验证码",
)


_BROWSER_ENV_JS = r"""
async () => {
    const safe = async (fn, fallback = null) => {
        try { return await fn(); } catch (_) { return fallback; }
    };
    const visible = (el) => {
        try {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
                style.display !== 'none' && style.visibility !== 'hidden' &&
                parseFloat(style.opacity || '1') > 0.05;
        } catch (_) {
            return false;
        }
    };
    const readWebgl = () => {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (!gl) return {supported: false};
        const dbg = gl.getExtension('WEBGL_debug_renderer_info');
        return {
            supported: true,
            vendor: gl.getParameter(gl.VENDOR),
            renderer: gl.getParameter(gl.RENDERER),
            unmaskedVendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : '',
            unmaskedRenderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : '',
        };
    };
    const readPermission = async (name) => {
        if (!navigator.permissions || !navigator.permissions.query) return 'unsupported';
        try {
            const status = await navigator.permissions.query({name});
            return status && status.state ? status.state : 'unknown';
        } catch (_) {
            return 'error';
        }
    };
    const bodyText = (document.body && document.body.innerText || '').replace(/\s+/g, ' ').trim();
    const keywords = __RISK_KEYWORDS__;
    const riskPrompts = [];
    if (bodyText) {
        for (const keyword of keywords) {
            const idx = bodyText.indexOf(keyword);
            if (idx >= 0) {
                riskPrompts.push({
                    keyword,
                    snippet: bodyText.slice(Math.max(0, idx - 40), Math.min(bodyText.length, idx + 100)),
                });
            }
        }
    }
    const visibleDialogs = Array.from(document.querySelectorAll('[role="dialog"], [role="alert"], .dialog, .modal, [class*="toast"], [class*="message"]'))
        .filter(visible)
        .slice(0, 20)
        .map((el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 240))
        .filter(Boolean);

    const uaData = await safe(async () => {
        if (!navigator.userAgentData) return null;
        const high = navigator.userAgentData.getHighEntropyValues
            ? await navigator.userAgentData.getHighEntropyValues([
                'architecture', 'bitness', 'model', 'platform', 'platformVersion',
                'uaFullVersion', 'fullVersionList',
            ])
            : {};
        return {
            brands: navigator.userAgentData.brands || [],
            mobile: navigator.userAgentData.mobile,
            platform: navigator.userAgentData.platform,
            highEntropy: high,
        };
    }, null);

    return {
        url: location.href,
        title: document.title,
        readyState: document.readyState,
        capturedAt: new Date().toISOString(),
        navigator: {
            userAgent: navigator.userAgent,
            webdriver: navigator.webdriver,
            platform: navigator.platform,
            vendor: navigator.vendor,
            productSub: navigator.productSub,
            language: navigator.language,
            languages: navigator.languages ? Array.from(navigator.languages) : [],
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory,
            maxTouchPoints: navigator.maxTouchPoints,
            cookieEnabled: navigator.cookieEnabled,
            doNotTrack: navigator.doNotTrack,
            plugins: Array.from(navigator.plugins || []).slice(0, 20).map((p) => ({
                name: p.name,
                filename: p.filename,
                description: p.description,
            })),
            mimeTypesLength: navigator.mimeTypes ? navigator.mimeTypes.length : null,
            userAgentData: uaData,
        },
        screen: {
            width: screen.width,
            height: screen.height,
            availWidth: screen.availWidth,
            availHeight: screen.availHeight,
            colorDepth: screen.colorDepth,
            pixelDepth: screen.pixelDepth,
        },
        viewport: {
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            outerWidth: window.outerWidth,
            outerHeight: window.outerHeight,
            devicePixelRatio: window.devicePixelRatio,
        },
        locale: {
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            dateTimeLocale: Intl.DateTimeFormat().resolvedOptions().locale,
        },
        permissions: {
            notifications: await readPermission('notifications'),
            geolocation: await readPermission('geolocation'),
            camera: await readPermission('camera'),
            microphone: await readPermission('microphone'),
        },
        webgl: readWebgl(),
        storage: {
            localStorageKeys: await safe(() => Object.keys(localStorage || {}).slice(0, 80), []),
            sessionStorageKeys: await safe(() => Object.keys(sessionStorage || {}).slice(0, 80), []),
        },
        riskPrompts,
        visibleDialogs,
    };
}
"""


def _launch_context_from_metadata(metadata: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(metadata, Mapping):
        return {}
    raw = metadata.get("_diagnostic_context")
    if not isinstance(raw, Mapping):
        return {}
    launch = raw.get("browser_launch")
    return dict(launch) if isinstance(launch, Mapping) else {}


async def collect_xhs_browser_environment(
    page: Page,
    metadata: Optional[Mapping[str, Any]] = None,
    *,
    stage: str = "",
) -> Dict[str, Any]:
    """Collect a sanitized browser environment snapshot for Xiaohongshu."""

    script = _BROWSER_ENV_JS.replace(
        "__RISK_KEYWORDS__",
        repr(list(RISK_PROMPT_KEYWORDS)),
    )
    snapshot: Dict[str, Any] = {
        "platform": "xiaohongshu",
        "stage": stage,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "launch_context": _launch_context_from_metadata(metadata),
        "page": {},
        "cookies": [],
        "notes": [
            "Cookie values are intentionally omitted.",
            "This snapshot is for pre-submit diagnosis and should not be used as publish-result attribution.",
        ],
    }

    try:
        raw = await page.evaluate(script)
        if isinstance(raw, dict):
            snapshot["page"] = raw
    except Exception as exc:
        snapshot["page_error"] = str(exc)

    try:
        context = page.context
        cookies = await context.cookies("https://creator.xiaohongshu.com")
        snapshot["cookies"] = [
            {
                "name": c.get("name", ""),
                "domain": c.get("domain", ""),
                "path": c.get("path", ""),
                "expires": c.get("expires"),
                "httpOnly": c.get("httpOnly"),
                "secure": c.get("secure"),
                "sameSite": c.get("sameSite"),
            }
            for c in cookies
        ]
        snapshot["cookie_count"] = len(cookies)
    except Exception as exc:
        snapshot["cookie_error"] = str(exc)

    return snapshot


async def attach_xhs_environment_snapshot(
    metadata: Dict[str, Any],
    page: Page,
    *,
    stage: str,
) -> Dict[str, Any]:
    """Attach the latest sanitized snapshot to metadata for the diagnostics bundle."""

    snapshot = await collect_xhs_browser_environment(page, metadata, stage=stage)
    ctx = metadata.get("_diagnostic_context")
    if not isinstance(ctx, dict):
        ctx = {}
        metadata["_diagnostic_context"] = ctx
    snapshots = ctx.get("xhs_environment_snapshots")
    if not isinstance(snapshots, list):
        snapshots = []
        ctx["xhs_environment_snapshots"] = snapshots
    snapshots.append(snapshot)
    ctx["xhs_environment_snapshot"] = snapshot
    return snapshot

