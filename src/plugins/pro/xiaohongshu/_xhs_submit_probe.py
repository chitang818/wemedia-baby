# -*- coding: utf-8 -*-
"""
xhs-publish-btn 发布钮探针与 closed Shadow 访问（步骤8 / 探针脚本共用）。

实采结论（2026-05-25）：
  - shadowRoot 为 closed，页面上下文不可访问
  - host.evaluate 内可通过 el._sr 访问 Shadow
  - 主提交钮：button.ce-btn.bg-red（文案「发布」或「定时发布」）
  - 排他钮：button.ce-btn.white「暂存离开」
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import Locator, Page

# closed Shadow：优先 _sr，其次 shadowRoot（open 时）
_GET_SHADOW_ROOT_JS = """(el) => {
    if (!el) return null;
    const sr = el._sr || el.shadowRoot;
    return (sr && typeof sr.querySelector === 'function') ? sr : null;
}"""

# 在宿主 locator 上 evaluate，读取 _sr 内红钮状态
_SR_RED_BUTTON_STATE_JS = """(el, primary) => {
    if (!el) return { ready: false, reason: 'no_host' };
    if (el.getAttribute('submit-disabled') === 'true') {
        return { ready: false, reason: 'submit_disabled' };
    }
    const sr = el._sr || el.shadowRoot;
    if (!sr || typeof sr.querySelector !== 'function') {
        return { ready: false, reason: 'no_shadow_access' };
    }
    const btn = sr.querySelector('button.ce-btn.bg-red');
    if (!btn) return { ready: false, reason: 'red_btn_missing' };
    const text = (btn.innerText || btn.textContent || '').trim();
    const r = btn.getBoundingClientRect();
    if (r.width < 20 || r.height < 8) {
        return { ready: false, reason: 'red_btn_no_size', text };
    }
    const excluded = (t) => !t || t.includes('暂存') || t.includes('草稿') || t.includes('离开');
    if (excluded(text)) return { ready: false, reason: 'red_btn_excluded', text };
    const expected = (el.getAttribute('submit-text') || primary || '').trim();
    if (expected === '定时发布' && text !== '定时发布') {
        return { ready: false, reason: 'text_mismatch', expected, text };
    }
    if (expected === '发布' && text.includes('定时发布')) {
        return { ready: false, reason: 'text_mismatch', expected, text };
    }
    return {
        ready: true,
        text,
        centerX: r.x + r.width / 2,
        centerY: r.y + r.height / 2,
        submitText: expected,
        submitDisabled: el.getAttribute('submit-disabled'),
    };
}"""

# 点击红钮（主路径）
_SR_CLICK_RED_BUTTON_JS = """(el, args) => {
    const primary = (args && args.primary) || '发布';
    const ignoreDisabled = !!(args && args.ignoreDisabled);
    if (!el) return { ok: false, reason: 'no_host' };
    if (!ignoreDisabled && el.getAttribute('submit-disabled') === 'true') {
        return { ok: false, reason: 'submit_disabled' };
    }
    const sr = el._sr || el.shadowRoot;
    if (!sr) return { ok: false, reason: 'no_shadow_access' };
    const btn = sr.querySelector('button.ce-btn.bg-red');
    if (!btn) return { ok: false, reason: 'red_btn_missing' };
    const text = (btn.innerText || btn.textContent || '').trim();
    const expected = (el.getAttribute('submit-text') || primary || '').trim();
    if (expected === '定时发布' && text !== '定时发布') {
        return { ok: false, reason: 'text_mismatch', expected, actual: text };
    }
    const r = btn.getBoundingClientRect();
    if (r.width < 20 || r.height < 8) {
        return { ok: false, reason: 'red_btn_no_size' };
    }
    btn.click();
    return { ok: true, text, method: '_sr_click' };
}"""

# 红钮中心坐标（鼠标兜底）
_SR_RED_BUTTON_CENTER_JS = """(el, args) => {
    const primary = (args && args.primary) || '发布';
    const ignoreDisabled = !!(args && args.ignoreDisabled);
    if (!el) return null;
    if (!ignoreDisabled && el.getAttribute('submit-disabled') === 'true') return null;
    const sr = el._sr || el.shadowRoot;
    if (!sr) return null;
    const btn = sr.querySelector('button.ce-btn.bg-red');
    if (!btn) return null;
    const text = (btn.innerText || btn.textContent || '').trim();
    const expected = (el.getAttribute('submit-text') || primary || '').trim();
    if (expected === '定时发布' && text !== '定时发布') return null;
    const r = btn.getBoundingClientRect();
    if (r.width < 20 || r.height < 8) return null;
    return { x: r.x + r.width / 2, y: r.y + r.height / 2, text };
}"""

# 宿主右下角估算坐标（_sr 失效兜底，2026-05-25 实测）
_HOST_OFFSET_CLICK_JS = """(el) => {
    if (!el) return null;
    const box = el.getBoundingClientRect();
    if (box.width < 100 || box.height < 20) return null;
    return { x: box.x + box.width - 120, y: box.y + 45 };
}"""

XHS_PUBLISH_BTN_SNAPSHOT_JS = """() => {
    const pickerSels = [
        'body > .post-time-date-picker-popover-class',
        '.post-time-date-picker-popover-class',
    ];
    let pickerOpen = false;
    for (const s of pickerSels) {
        const el = document.querySelector(s);
        if (!el) continue;
        const r = el.getBoundingClientRect();
        const st = window.getComputedStyle(el);
        if (r.width > 0 && r.height > 0 &&
            st.display !== 'none' && st.visibility !== 'hidden') {
            pickerOpen = true;
            break;
        }
    }
    const wrap = document.querySelector('.publish-page-content-settings .post-time-wrapper')
        || document.querySelector('.post-time-wrapper');
    let schedule = { found: false };
    if (wrap) {
        const cb = wrap.querySelector("input[type='checkbox']");
        const timeInp = wrap.querySelector("input[type='text'], input.d-text");
        schedule = {
            found: true,
            checkboxChecked: !!(cb && cb.checked),
            simulatorClass: (wrap.querySelector('.d-switch-simulator') || {}).className || '',
            timeInputValue: timeInp ? (timeInp.value || '') : '',
        };
    }
    const ae = document.activeElement;
    const focusInSchedule = !!(ae && wrap && wrap.contains(ae));

    const readShadowButtons = (el) => {
        const sr = el._sr || el.shadowRoot;
        if (!sr) return { hasSr: !!el._sr, hasShadowRoot: !!el.shadowRoot, buttons: [] };
        const all = [...sr.querySelectorAll('button.ce-btn')];
        return {
            hasSr: !!el._sr,
            hasShadowRoot: !!el.shadowRoot,
            buttons: all.map((btn, i) => {
                const r = btn.getBoundingClientRect();
                return {
                    index: i,
                    text: (btn.innerText || btn.textContent || '').trim(),
                    className: btn.className || '',
                    disabled: !!btn.disabled,
                    width: Math.round(r.width),
                    height: Math.round(r.height),
                };
            }),
        };
    };

    const hosts = [...document.querySelectorAll('xhs-publish-btn')];
    const hostSnapshots = hosts.map((el, idx) => {
        const shadow = readShadowButtons(el);
        return {
            index: idx,
            isPublish: el.getAttribute('is-publish') || '',
            submitText: el.getAttribute('submit-text') || '',
            submitDisabled: el.getAttribute('submit-disabled') || '',
            hasSr: shadow.hasSr,
            hasShadowRoot: shadow.hasShadowRoot,
            shadowButtonCount: shadow.buttons.length,
            shadowButtons: shadow.buttons,
        };
    });
    return {
        url: location.href,
        pickerOpen,
        schedule,
        focusInSchedule,
        activeElementTag: ae ? (ae.tagName || '') : '',
        hostCount: hosts.length,
        hosts: hostSnapshots,
    };
}"""

SHADOW_SUBMIT_EXCLUDE_SUBSTRINGS: tuple[str, ...] = (
    "暂存",
    "草稿",
    "离开",
)

# 发布成功 URL 特征（两次实采验证）
SUCCESS_URL_MARKERS: tuple[str, ...] = (
    "published=true",
    "/publish/success",
    "/manage/note",
    "/new/note/manage",
)


def is_shadow_submit_candidate_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return not any(part in t for part in SHADOW_SUBMIT_EXCLUDE_SUBSTRINGS)


def pick_primary_host(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    hosts: List[Dict[str, Any]] = list(snapshot.get("hosts") or [])
    for h in hosts:
        if str(h.get("isPublish") or "").lower() == "true":
            return h
    return hosts[0] if hosts else {}


def summarize_snapshot_for_log(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    host = pick_primary_host(snapshot)
    red_btns = [
        b for b in (host.get("shadowButtons") or [])
        if "bg-red" in str(b.get("className") or "")
        or is_shadow_submit_candidate_text(str(b.get("text") or ""))
        and "发布" in str(b.get("text") or "")
    ]
    return {
        "submit_text": host.get("submitText") or "",
        "submit_disabled": str(host.get("submitDisabled") or "").lower() == "true",
        "has_sr": bool(host.get("hasSr")),
        "schedule_picker_open": bool(snapshot.get("pickerOpen")),
        "focus_in_schedule": bool(snapshot.get("focusInSchedule")),
        "schedule_on": bool((snapshot.get("schedule") or {}).get("checkboxChecked")),
        "shadow_button_count": host.get("shadowButtonCount", 0),
        "shadow_buttons": [
            {"text": b.get("text"), "w": b.get("width"), "h": b.get("height")}
            for b in (host.get("shadowButtons") or [])
        ],
        "red_button_ready": len(red_btns) > 0,
        "host_count": snapshot.get("hostCount", 0),
    }


def url_indicates_publish_success(url: str) -> bool:
    u = (url or "").lower()
    if not u or "xiaohongshu.com" not in u:
        return False
    if "creator.xiaohongshu.com" in u and "/publish/publish" in u:
        if "from=homepage" in u or "target=video" in u:
            return False
    for marker in SUCCESS_URL_MARKERS:
        if marker in u:
            return True
    if "creator.xiaohongshu.com" in u and "/publish/publish" not in u:
        return True
    return False


async def snapshot_xhs_publish_btn(page: Page) -> Dict[str, Any]:
    try:
        raw = await page.evaluate(XHS_PUBLISH_BTN_SNAPSHOT_JS)
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {"hostCount": 0, "hosts": [], "error": "evaluate_failed"}


async def evaluate_sr_red_button_state(
    host: Locator, primary_label: str,
) -> Dict[str, Any]:
    try:
        raw = await host.evaluate(_SR_RED_BUTTON_STATE_JS, primary_label)
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {"ready": False, "reason": "evaluate_failed"}


async def click_via_sr(
    host: Locator,
    primary_label: str,
    *,
    ignore_host_disabled: bool = False,
) -> Dict[str, Any]:
    try:
        raw = await host.evaluate(
            _SR_CLICK_RED_BUTTON_JS,
            {"primary": primary_label, "ignoreDisabled": ignore_host_disabled},
        )
        if isinstance(raw, dict):
            return raw
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    return {"ok": False, "reason": "evaluate_failed"}


async def resolve_sr_click_center(
    host: Locator,
    primary_label: str,
    *,
    ignore_host_disabled: bool = False,
) -> Tuple[Optional[float], Optional[float], str]:
    try:
        pt = await host.evaluate(
            _SR_RED_BUTTON_CENTER_JS,
            {"primary": primary_label, "ignoreDisabled": ignore_host_disabled},
        )
        if pt and pt.get("x") is not None and pt.get("y") is not None:
            return (
                float(pt["x"]),
                float(pt["y"]),
                f"_sr_center:{pt.get('text') or ''}",
            )
    except Exception:
        pass
    try:
        pt = await host.evaluate(_HOST_OFFSET_CLICK_JS)
        if pt and pt.get("x") is not None:
            return float(pt["x"]), float(pt["y"]), "host_offset_fallback"
    except Exception:
        pass
    return None, None, ""


async def probe_pierce_submit_selectors(
    page: Page, selectors: List[str],
) -> Dict[str, Any]:
    """探测 pierce 选择器（closed Shadow 下通常 count=0，仅诊断用）。"""
    out: Dict[str, Any] = {}
    for sel in selectors:
        item: Dict[str, Any] = {"selector": sel, "count": 0}
        try:
            loc = page.locator(sel)
            count = await loc.count()
            item["count"] = count
            if count > 0:
                first = loc.first
                try:
                    item["text"] = ((await first.inner_text(timeout=2000)) or "").strip()[:80]
                except Exception:
                    item["text"] = ""
        except Exception as exc:
            item["error"] = str(exc)
        out[sel] = item
    return out
