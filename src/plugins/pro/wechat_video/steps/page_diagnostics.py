# -*- coding: utf-8 -*-
"""视频号发布页诊断工具。

仅用于本应用 Playwright 发布流程内的故障分析，不依赖 Codex Chrome 扩展。
"""

import json
import logging
from typing import Any

from playwright.async_api import Page


async def log_page_diagnostics(
    page: Page,
    logger: logging.Logger,
    reason: str,
    *,
    level: int = logging.WARNING,
    max_items: int = 40,
) -> None:
    """输出当前页面关键 DOM 摘要，帮助定位发布页结构变化。"""
    try:
        summary: Any = await page.evaluate(
            """(maxItems) => {
                const roots = [document, ...Array.from(document.querySelectorAll('wujie-app'))
                    .map((w) => w.shadowRoot)
                    .filter(Boolean)];
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const brief = (el, rootIndex) => {
                    const rect = el.getBoundingClientRect();
                    return {
                        rootIndex,
                        tag: el.tagName,
                        id: el.id || '',
                        className: String(el.className || ''),
                        role: el.getAttribute('role') || '',
                        type: el.getAttribute('type') || '',
                        placeholder: el.getAttribute('placeholder') || '',
                        text: (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 180),
                        rect: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                        },
                        outerHTML: el.outerHTML.slice(0, 500),
                    };
                };
                const keyword = /上传|添加|图片|图文|发表|描述|标题|原创|位置|定时|预览|删除|封面|正文|内容|文件|相册/;
                const selector = [
                    'button',
                    'input',
                    'textarea',
                    '[contenteditable]',
                    '[role="button"]',
                    'a',
                    '.upload-content',
                    '[class*="upload"]',
                    '[class*="image"]',
                    '[class*="photo"]',
                    '[class*="form"]',
                    '[class*="desc"]',
                    '[class*="title"]',
                    '[class*="post"]',
                    '[class*="file"]',
                ].join(',');
                const hits = [];
                roots.forEach((root, rootIndex) => {
                    for (const el of root.querySelectorAll(selector)) {
                        if (!visible(el)) continue;
                        const haystack = [
                            el.textContent || '',
                            el.getAttribute('placeholder') || '',
                            String(el.className || ''),
                            el.getAttribute('type') || '',
                        ].join(' ');
                        if (!keyword.test(haystack)) continue;
                        hits.push(brief(el, rootIndex));
                        if (hits.length >= maxItems) break;
                    }
                });
                return {
                    url: location.href,
                    title: document.title,
                    wujieCount: document.querySelectorAll('wujie-app').length,
                    hits,
                };
            }""",
            max_items,
        )
        logger.log(
            level,
            "[视频号] 页面诊断(%s): %s",
            reason,
            json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
        )
    except Exception as e:
        logger.log(level, "[视频号] 页面诊断失败(%s): %s", reason, e)
