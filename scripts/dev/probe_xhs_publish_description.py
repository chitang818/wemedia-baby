# -*- coding: utf-8 -*-
"""
小红书视频发布页：描述编辑器与话题输入 DOM 探针（只读诊断）。

用法（需已登录创作者中心，建议复用账号 browser profile）：
  python scripts/dev/probe_xhs_publish_description.py
  python scripts/dev/probe_xhs_publish_description.py --headed
  python scripts/dev/probe_xhs_publish_description.py --user-data-dir "%LOCALAPPDATA%\\WeMediaBaby\\data\\user_data"

输出：test-reports/xhs-probe/description_probe.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from playwright.async_api import async_playwright

from src.plugins.pro.xiaohongshu.selectors import Selectors

PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"
PROBE_TOPICS = ["蔬菜种植", "转色增甜", "鸭血水溶肥", "大田作物", "遥马农业"]

CHIP_COUNT_JS = """(root) => {
    if (!root) return 0;
    const nodes = root.querySelectorAll(
        'a[class*="tag"], span[class*="tag"], [class*="topic-tag"], [class*="hashtag"], [class*="topic-item"], a[data-topic]'
    );
    let n = 0;
    nodes.forEach(el => {
        const t = (el.textContent || '').trim();
        if (t && (t.startsWith('#') || /topic|tag|hashtag/i.test(el.className || ''))) n++;
    });
    return n;
}"""

EDITOR_INFO_JS = """(root) => ({
    placeholder: root.getAttribute('data-placeholder') || '',
    className: root.className || '',
    innerTextLen: (root.innerText || '').length
})"""


async def _find_editor(page):
    for sel in Selectors.PUBLISH.get("DESC_EDITOR") or []:
        loc = page.locator(sel).first
        try:
            if await loc.count() > 0 and await loc.is_visible():
                return loc, sel
        except Exception:
            continue
    return None, None


async def _probe_editor(page) -> dict:
    edit_box, sel = await _find_editor(page)
    if not edit_box:
        return {"error": "DESC_EDITOR not found"}
    handle = await edit_box.element_handle()
    info = await page.evaluate(EDITOR_INFO_JS, handle)
    chips = await page.evaluate(CHIP_COUNT_JS, handle)
    return {"selector": sel, "chipCount": chips, **info}


async def _probe_toolbar_buttons(page, edit_box) -> list:
    found = []
    scope = edit_box.locator("xpath=ancestor::div[position()<=10]")
    for sel in Selectors.PUBLISH.get("TOPIC_ENTRY_BTN") or []:
        try:
            loc = scope.locator(sel).first
            if await loc.count() > 0:
                found.append({"selector": sel, "scoped": True, "visible": await loc.is_visible()})
        except Exception:
            pass
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                found.append({"selector": sel, "scoped": False, "visible": await loc.is_visible()})
        except Exception:
            pass
    return found


async def _type_one_topic(
    page, edit_box, label: str, *, use_topic_btn: bool
) -> dict:
    await edit_box.click()
    await page.keyboard.press("Control+End")
    await page.wait_for_timeout(120)
    if use_topic_btn:
        for sel in Selectors.PUBLISH.get("TOPIC_ENTRY_BTN") or []:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(timeout=2000)
                    await page.wait_for_timeout(150)
                    break
            except Exception:
                continue
        await edit_box.click()
        await page.keyboard.press("Control+End")
    else:
        await page.keyboard.type("#")
    await page.keyboard.type(label, delay=40)
    await page.wait_for_timeout(900)
    for sel in Selectors.PUBLISH.get("TOPIC_SUGGESTION") or []:
        try:
            item = page.locator(sel).filter(has_text=label).first
            if await item.count() > 0 and await item.is_visible():
                await item.click(timeout=1000)
                await page.wait_for_timeout(200)
                break
        except Exception:
            continue
    else:
        await page.keyboard.press("ArrowDown")
        await page.wait_for_timeout(80)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(150)
    await page.keyboard.press("Space")
    await page.wait_for_timeout(650)
    handle = await edit_box.element_handle()
    chips = await page.evaluate(CHIP_COUNT_JS, handle)
    text = await page.evaluate("el => el.innerText || ''", handle)
    return {
        "label": label,
        "use_topic_btn": use_topic_btn,
        "chipCount": chips,
        "has_double_hash": "##" in text,
        "innerText_tail": text[-80:] if text else "",
    }


async def _run_experiment(page, edit_box, mode: str) -> list:
    await edit_box.click()
    await page.keyboard.press("Control+A")
    await page.keyboard.press("Backspace")
    await page.wait_for_timeout(300)
    await page.keyboard.type("探针正文测试 ", delay=30)
    results = []
    for i, label in enumerate(PROBE_TOPICS):
        use_btn = mode == "A" or (mode == "B" and i == 0)
        row = await _type_one_topic(page, edit_box, label, use_topic_btn=use_btn)
        row["index"] = i + 1
        row["mode"] = mode
        results.append(row)
    return results


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--user-data-dir", default="")
    parser.add_argument("--wait-login-sec", type=int, default=90)
    args = parser.parse_args()

    out_dir = _ROOT / "test-reports" / "xhs-probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"publish_url": PUBLISH_URL, "experiments": {}}

    async with async_playwright() as p:
        if args.user_data_dir:
            context = await p.chromium.launch_persistent_context(
                args.user_data_dir,
                headless=not args.headed,
                channel="chrome",
            )
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            browser = await p.chromium.launch(headless=not args.headed, channel="chrome")
            context = await browser.new_context()
            page = await context.new_page()

        await page.goto(PUBLISH_URL, wait_until="domcontentloaded")
        print(f"请在 {args.wait_login_sec}s 内完成登录并进入视频发布页（含描述编辑器）…")
        await page.wait_for_timeout(args.wait_login_sec * 1000)

        edit_box, _ = await _find_editor(page)
        if not edit_box:
            report["error"] = "未找到描述编辑器，请确认已在发布页"
            out_path = out_dir / "description_probe.json"
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            await context.close()
            return 1

        report["editor"] = await _probe_editor(page)
        report["topic_entry_buttons"] = await _probe_toolbar_buttons(page, edit_box)
        report["experiments"]["A_every_topic_btn"] = await _run_experiment(page, edit_box, "A")
        report["experiments"]["B_first_topic_btn_only"] = await _run_experiment(page, edit_box, "B")

        out_path = out_dir / "description_probe.json"
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"探针结果已写入: {out_path}")
        await context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
