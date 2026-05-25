# -*- coding: utf-8 -*-
"""小红书发布页 URL 净化：去掉 openFilePicker 并关闭系统自动文件对话框。"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.wait_helper import PluginWaitHelper

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"
PUBLISH_TARGET_URLS = {
    "image": f"{PUBLISH_URL}?from=homepage&target=image",
    "video": f"{PUBLISH_URL}?from=homepage&target=video",
}


def clean_publish_url(file_type: str) -> str:
    """返回无 openFilePicker 的发布页 URL（与步骤2 直接导航一致）。"""
    ft = (file_type or "video").lower()
    return PUBLISH_TARGET_URLS.get(ft, PUBLISH_TARGET_URLS["video"])


def url_has_auto_file_picker(url: str) -> bool:
    """检测 URL 是否含 openFilePicker 查询参数（大小写不敏感）。"""
    try:
        query = parse_qs(urlparse(url or "").query, keep_blank_values=True)
    except Exception:
        return "openfilepicker" in (url or "").lower()
    for key in query:
        if key.lower() == "openfilepicker":
            return True
    return "openfilepicker=true" in (url or "").lower()


def strip_open_file_picker_from_url(url: str, *, file_type: str = "video") -> str:
    """从任意发布页 URL 移除 openFilePicker，保留其余 query（若无 target 则补全）。"""
    try:
        parsed = urlparse(url or "")
        if not parsed.scheme or not parsed.netloc:
            return clean_publish_url(file_type)
        query = parse_qs(parsed.query, keep_blank_values=True)
        cleaned = {
            k: v for k, v in query.items() if k.lower() != "openfilepicker"
        }
        if not any(k.lower() == "target" for k in cleaned):
            ft = (file_type or "video").lower()
            cleaned["target"] = [ft]
        if not any(k.lower() == "from" for k in cleaned):
            cleaned["from"] = ["homepage"]
        flat = [(k, val) for k, vals in cleaned.items() for val in vals]
        new_query = urlencode(flat)
        return urlunparse(parsed._replace(query=new_query))
    except Exception:
        return clean_publish_url(file_type)


async def dismiss_native_file_dialog(page: Page) -> None:
    """尽量关闭页面自动弹出的 Windows 系统「打开」对话框。"""
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(200)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(150)
    except Exception as e:
        logger.debug("关闭系统文件对话框时异常（可忽略）: %s", e)


async def ensure_publish_page_without_file_picker(
    page: Page,
    file_type: str,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    pause_callback=None,
) -> Optional[PublishResult]:
    """若 URL 含 openFilePicker：关闭系统对话框并导航到无弹窗 URL。"""
    metadata = metadata or {}
    ft = (file_type or "video").lower()
    clean_url = clean_publish_url(ft)

    try:
        current = page.url or ""
    except Exception:
        current = ""

    needs_goto = url_has_auto_file_picker(current)
    if not needs_goto:
        return None

    logger.info(
        "检测到 openFilePicker=true，关闭系统文件选择器并导航至无弹窗 URL: %s",
        clean_url,
    )
    USER_LOG.info("[发布页] 已关闭页面自动文件选择器，切换为自动化上传模式")

    await dismiss_native_file_dialog(page)
    try:
        await page.goto(clean_url, timeout=30000, wait_until="domcontentloaded")
    except Exception as e:
        logger.warning("导航至无 openFilePicker 发布页失败: %s", e)
        return PublishResult(
            success=False,
            error_message=f"页面自动弹出文件选择器，切换自动化上传模式失败: {e}",
            failed_step="进入发布页",
        )

    speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))

    async def _url_clean() -> bool:
        try:
            return not url_has_auto_file_picker(page.url or "")
        except Exception:
            return False

    confirmed = await PluginWaitHelper.wait_for_condition(
        page,
        _url_clean,
        timeout_ms=int(5000 * speed_rate),
        poll_interval_ms=300,
        pause_callback=pause_callback,
    )
    if not confirmed:
        try:
            still = page.url or ""
        except Exception:
            still = ""
        return PublishResult(
            success=False,
            error_message=(
                "页面自动弹出文件选择器，未能切换到自动化上传模式"
                f"（url仍含 openFilePicker: {still}）"
            ),
            failed_step="进入发布页",
        )

    logger.info("发布页 URL 已净化: %s", page.url)
    return None
