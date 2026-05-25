# -*- coding: utf-8 -*-
"""
小红书视频发布页：定时发布区域 DOM 探针（只读诊断）。

用法（需已登录创作者中心，建议复用账号 browser profile）：
  python scripts/dev/probe_xhs_publish_schedule.py
  python scripts/dev/probe_xhs_publish_schedule.py --headed
  python scripts/dev/probe_xhs_publish_schedule.py --user-data-dir "%LOCALAPPDATA%\\WeMediaBaby\\data\\xiaohongshu\\profile_xxx\\browser\\user_data"

输出：test-reports/xhs-probe/schedule_probe.json
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

PUBLISH_URL = (
    "https://creator.xiaohongshu.com/publish/publish"
    "?from=homepage&target=video"
)

SCHEDULE_PROBE_JS = """() => {
    const wrap = document.querySelector('.publish-page-content-settings .post-time-wrapper')
        || document.querySelector('.post-time-wrapper');
    if (!wrap) return { found: false };
    const cb = wrap.querySelector("input[type='checkbox']");
    const sim = wrap.querySelector('.d-switch-simulator');
    const inputs = wrap.querySelectorAll("input[type='text'], input.d-text");
    const times = [];
    inputs.forEach(inp => times.push({
        type: inp.type,
        className: inp.className || '',
        value: inp.value || '',
        visible: !!(inp.offsetWidth && inp.offsetHeight)
    }));
    return {
        found: true,
        checkboxChecked: !!(cb && cb.checked),
        simulatorClass: sim ? (sim.className || '') : '',
        timeInputCount: times.length,
        timeInputs: times,
        innerTextSnippet: (wrap.innerText || '').slice(0, 120),
    };
}"""


async def _probe_schedule_dom(page) -> dict:
    base = await page.evaluate(SCHEDULE_PROBE_JS)
    selectors_hit: dict[str, bool] = {}
    for key in (
        "SCHEDULE_WRAPPER",
        "SCHEDULE_CHECKBOX",
        "SCHEDULE_SWITCH",
        "SCHEDULE_TIME_DISPLAY",
        "SCHEDULE_DATE_PICKER",
    ):
        for sel in Selectors.SETTINGS.get(key, []) or []:
            try:
                loc = page.locator(sel).first
                selectors_hit[sel] = (await loc.count() > 0)
            except Exception:
                selectors_hit[sel] = False
    return {"dom": base, "selectors": selectors_hit}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--user-data-dir", default="")
    parser.add_argument("--wait-login-sec", type=int, default=90)
    args = parser.parse_args()

    out_dir = _ROOT / "test-reports" / "xhs-probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"publish_url": PUBLISH_URL}

    async with async_playwright() as p:
        if args.user_data_dir:
            context = await p.chromium.launch_persistent_context(
                args.user_data_dir,
                headless=not args.headed,
                channel="chrome",
            )
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            browser = await p.chromium.launch(
                headless=not args.headed, channel="chrome"
            )
            context = await browser.new_context()
            page = await context.new_page()

        await page.goto(PUBLISH_URL, wait_until="domcontentloaded")
        print(
            f"请在 {args.wait_login_sec}s 内完成登录并进入视频发布设置页（含「更多设置」）…"
        )
        await page.wait_for_timeout(args.wait_login_sec * 1000)

        report["before_click"] = await _probe_schedule_dom(page)

        try:
            wrap = page.locator(".post-time-wrapper").filter(has_text="定时发布").first
            sim = wrap.locator(".d-switch-simulator").first
            if await sim.count() > 0:
                await sim.click(timeout=3000)
                await page.wait_for_timeout(800)
                report["after_switch_click"] = await _probe_schedule_dom(page)
                inp = wrap.locator("input[type='text']").first
                if await inp.count() > 0:
                    await inp.click(timeout=3000)
                    await page.wait_for_timeout(500)
                    picker_visible = await page.locator(
                        ".post-time-date-picker-popover-class"
                    ).first.is_visible()
                    report["picker_visible_after_time_click"] = picker_visible
        except Exception as e:
            report["interaction_error"] = str(e)

        out_path = out_dir / "schedule_probe.json"
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"探针结果已写入: {out_path}")
        await context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
