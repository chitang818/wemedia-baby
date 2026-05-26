# -*- coding: utf-8 -*-
"""
小红书视频发布页：xhs-publish-btn / 定时发布提交钮 DOM 探针（只读诊断）。

用法（需已登录且发布页含 xhs-publish-btn，建议复用账号 browser profile）：
  python scripts/dev/probe_xhs_publish_submit.py --headed
  python scripts/dev/probe_xhs_publish_submit.py --user-data-dir "%LOCALAPPDATA%\\WeMediaBaby\\data\\xiaohongshu\\profile_xxx\\browser\\user_data"
  python scripts/dev/probe_xhs_publish_submit.py --discover-profile --headed

输出：test-reports/xhs-probe/submit_probe.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from playwright.async_api import async_playwright

from src.plugins.pro.xiaohongshu._xhs_submit_probe import (
    probe_pierce_submit_selectors,
    snapshot_xhs_publish_btn,
)
from src.plugins.pro.xiaohongshu.selectors import Selectors

PUBLISH_URL = (
    "https://creator.xiaohongshu.com/publish/publish"
    "?from=homepage&target=video"
)


def _discover_user_data_dir(platform: str = "xiaohongshu") -> str:
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "WeMediaBaby" / "data" / platform
    if not base.is_dir():
        return ""
    candidates = sorted(
        base.glob("profile_*/browser/user_data"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    for path in candidates:
        if path.is_dir():
            return str(path)
    return ""


async def _capture_state(page, label: str) -> dict:
    snap = await snapshot_xhs_publish_btn(page)
    pierce = await probe_pierce_submit_selectors(
        page, list(Selectors.PUBLISH.get("SUBMIT_BTN_SHADOW", []) or []),
    )
    return {
        "label": label,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "snapshot": snap,
        "pierce_selectors": pierce,
    }


async def _poll_submit_disabled_clear(page, timeout_sec: int = 30) -> dict:
    """轮询 submit-disabled 变为非 true。"""
    from src.plugins.pro.xiaohongshu._xhs_submit_probe import pick_primary_host

    started = asyncio.get_event_loop().time()
    history: list[dict] = []
    while asyncio.get_event_loop().time() - started < timeout_sec:
        snap = await snapshot_xhs_publish_btn(page)
        host = pick_primary_host(snap) or {}
        dis = str(host.get("submitDisabled") or "").lower()
        history.append({
            "elapsed_sec": round(asyncio.get_event_loop().time() - started, 2),
            "submit_disabled": dis,
            "submit_text": host.get("submitText"),
            "picker_open": snap.get("pickerOpen"),
            "focus_in_schedule": snap.get("focusInSchedule"),
        })
        if dis not in ("true", "1"):
            return {"cleared": True, "elapsed_sec": history[-1]["elapsed_sec"], "history": history}
        await page.wait_for_timeout(500)
    return {"cleared": False, "history": history}


async def _unlock_schedule_ui(page) -> None:
    """复现步骤7/8：关浮层 + 失焦。"""
    from src.plugins.pro.xiaohongshu.steps._schedule_picker import unlock_before_submit

    await unlock_before_submit(page, lambda ms: ms)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--user-data-dir", default="")
    parser.add_argument("--discover-profile", action="store_true")
    parser.add_argument("--wait-login-sec", type=int, default=90)
    parser.add_argument("--skip-interaction", action="store_true")
    args = parser.parse_args()

    user_data = args.user_data_dir.strip()
    if args.discover_profile and not user_data:
        user_data = _discover_user_data_dir()
        if user_data:
            print(f"已自动选用 profile: {user_data}")

    out_dir = _ROOT / "test-reports" / "xhs-probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"publish_url": PUBLISH_URL, "user_data_dir": user_data or None}

    async with async_playwright() as p:
        if user_data:
            context = await p.chromium.launch_persistent_context(
                user_data,
                headless=not args.headed,
                channel="chrome",
            )
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            browser = await p.chromium.launch(
                headless=not args.headed, channel="chrome",
            )
            context = await browser.new_context()
            page = await context.new_page()

        await page.goto(PUBLISH_URL, wait_until="domcontentloaded")
        print(
            f"请在 {args.wait_login_sec}s 内进入视频发布页（已上传素材、可见 xhs-publish-btn）…",
        )
        await page.wait_for_timeout(args.wait_login_sec * 1000)

        snap0 = await snapshot_xhs_publish_btn(page)
        report["initial_host_count"] = snap0.get("hostCount", 0)
        if not snap0.get("hostCount"):
            report["warning"] = (
                "未检测到 xhs-publish-btn：请先上传视频并填必填项，或检查登录态"
            )
            report["state_a_immediate"] = await _capture_state(page, "no_host")
        else:
            report["state_a_immediate"] = await _capture_state(page, "immediate")

            if not args.skip_interaction:
                try:
                    wrap = page.locator(".post-time-wrapper").filter(
                        has_text="定时发布",
                    ).first
                    sim = wrap.locator(".d-switch-simulator").first
                    if await sim.count() > 0:
                        cls = (await sim.get_attribute("class") or "").lower()
                        if "checked" in cls or "unchecked" not in cls:
                            await sim.click(timeout=3000)
                            await page.wait_for_timeout(400)
                            await sim.click(timeout=3000)
                            await page.wait_for_timeout(600)
                        else:
                            await sim.click(timeout=3000)
                            await page.wait_for_timeout(800)

                    report["state_b_schedule_on"] = await _capture_state(
                        page, "schedule_on_picker_maybe_open",
                    )

                    inp = wrap.locator("input[type='text']").first
                    if await inp.count() > 0:
                        await inp.click(timeout=3000)
                        await page.wait_for_timeout(500)
                        future = (datetime.now() + timedelta(days=1)).strftime(
                            "%Y-%m-%d %H:%M",
                        )
                        await inp.fill(future)
                        await page.wait_for_timeout(400)

                    await _unlock_schedule_ui(page)
                    await page.wait_for_timeout(500)
                    report["state_c_schedule_ready"] = await _capture_state(
                        page, "schedule_ready_after_unlock",
                    )
                    report["submit_disabled_poll"] = await _poll_submit_disabled_clear(
                        page, timeout_sec=30,
                    )
                except Exception as e:
                    report["interaction_error"] = str(e)

        try:
            await page.screenshot(
                path=str(out_dir / "submit_probe_screenshot.png"), full_page=True,
            )
        except Exception as e:
            report["screenshot_error"] = str(e)

        out_path = out_dir / "submit_probe.json"
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(f"探针结果已写入: {out_path}")
        await context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
