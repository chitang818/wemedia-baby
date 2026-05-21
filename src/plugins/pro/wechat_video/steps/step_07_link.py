# -*- coding: utf-8 -*-
"""
步骤7：链接设置（购物车商品挂载）
文件路径: src/plugins/pro/wechat_video/steps/step_07_link.py

依据：docs/03插件系统/OpenClaw 报告分析报告/视频号_购物车功能 DOM 分析报告_20260402.md

流程（均在 wujie-app Shadow DOM 内，除说明外）：
  1. 点击 .link-display-wrap 展开链接类型
  2. 点击 .link-option-item 中文案为「商品」的项
  3. 点击 .link-input-wrap .post-component-choose-wrap .content-wrap 打开 add-commodity-dialog
  4. 在弹窗 input[placeholder*="商品名称"] 填入搜索内容并触发 input
  5. 点击 .search-btn button「筛选」
  6. 等待 .ant-table-tbody tr，点击首行选中
  7. 点击弹窗内已启用的 weui-desktop-btn_primary「添加」类按钮
  8. 校验弹窗 display:none

若页面已是「商品」且出现「选择需要添加的商品」，可跳过步骤 1～2，直接步骤 3。

字段依赖：
  - metadata['cart_info']：publish_executor 统一注入，视频号对应 channels_id_or_link；
                            纯字符串直接使用，JSON 格式取 cart / channels_id_or_link / link / url 键。
  非空时执行购物车挂载，否则跳过本步骤。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..wujie_shadow import WUJIE_SHADOW_ROOT_JS as _WUJIE

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


def _effective_cart_search_text(metadata: Dict[str, Any]) -> str:
    """从任务 metadata 的 cart_info 解析要在弹窗里搜索的商品名称/编码/链接。

    cart_info 由 publish_executor 统一注入，视频号对应 channels_id_or_link：
      - 纯字符串：直接使用
      - JSON {"cart": "...", ...}：取 cart / channels_id_or_link / link / url 键
    """
    raw = metadata.get("cart_info")
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    if s.startswith("{"):
        try:
            d = json.loads(s)
            if isinstance(d, dict):
                for k in ("channels_id_or_link", "cart", "link", "url"):
                    v = (d.get(k) or "").strip()
                    if v:
                        return v
        except (json.JSONDecodeError, TypeError):
            pass
        # JSON 无法解析出有效链接时退回整段原文，避免静默丢配置
    return s


def _commodity_dialog_visible_fn() -> str:
    """Playwright page.evaluate 用：弹窗 add-commodity-dialog 是否可见。"""
    return f"""() => {{
        const shadow = {_WUJIE};
        if (!shadow) return false;
        const d = shadow.querySelector('div.add-commodity-dialog');
        if (!d) return false;
        const st = window.getComputedStyle(d);
        return st.display !== 'none' && st.visibility !== 'hidden';
    }}"""


class LinkSettingStep(BasePublishStep):
    """链接设置步骤：挂载视频号购物车商品（橱窗商品搜索）。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        search_text = _effective_cart_search_text(metadata)
        logger.info("[视频号] 步骤7：链接设置（购物车）")

        if not search_text:
            logger.info("[视频号] 未配置 cart_info，跳过链接设置")
            return None

        logger.info("[视频号] 购物车搜索内容长度=%s", len(search_text))
        USER_LOG.info("[视频号] 正在挂载购物车商品…")

        # ---- 优先：已是「商品」类型且可点「选择需要添加的商品」----
        direct_open = await page.evaluate(
            f"""() => {{
            const shadow = {_WUJIE};
            if (!shadow) return 'no_shadow';
            const cw = shadow.querySelector('div.link-input-wrap div.post-component-choose-wrap div.content-wrap');
            if (!cw) return 'no_target';
            const t = (cw.textContent || '');
            if (!t.includes('选择需要添加的商品')) return 'skip';
            cw.click();
            return 'ok';
        }}"""
        )
        if direct_open == "ok":
            logger.info("[视频号] 已处于「商品」链接类型，直接打开商品选择弹窗")
        elif direct_open in ("no_shadow", "no_target", "skip"):
            # ---- 步骤 1：点击「选择链接」----
            # 商品已选中时显示 choosen-link-wrap，未选中时显示 link-display-wrap，两者均需支持
            r1 = await page.evaluate(
                f"""() => {{
                const shadow = {_WUJIE};
                if (!shadow) return 'no_shadow';
                const el = shadow.querySelector('div.post-link-wrap div.link-display-wrap')
                        || shadow.querySelector('div.post-link-wrap div.choosen-link-wrap');
                if (!el) return 'no_link_display';
                el.click();
                return 'ok';
            }}"""
            )
            if r1 != "ok":
                logger.warning("[视频号] 步骤7：点击 link-display-wrap/choosen-link-wrap 失败: %s", r1)
                return PublishResult(
                    success=False,
                    error_message="未找到「选择链接」区域（link-display-wrap / choosen-link-wrap），无法挂载购物车",
                    failed_step="LinkSettingStep",
                )
            logger.info("[视频号] 已点击 link-display-wrap（展开链接类型）")
            await page.wait_for_timeout(500)

            # ---- 步骤 2：选择「商品」----
            r2 = await page.evaluate(
                f"""() => {{
                const shadow = {_WUJIE};
                if (!shadow) return 'no_shadow';
                const items = Array.from(shadow.querySelectorAll('div.link-option-item'));
                const hit = items.find((i) => {{
                    const x = (i.textContent || '').replace(/\\s+/g, '').trim();
                    return x === '商品';
                }});
                if (!hit) return 'not_found';
                hit.click();
                return 'ok';
            }}"""
            )
            if r2 != "ok":
                logger.warning("[视频号] 步骤7：未点到「商品」选项: %s", r2)
                return PublishResult(
                    success=False,
                    error_message="未找到链接类型「商品」（link-option-item），无法挂载购物车",
                    failed_step="LinkSettingStep",
                )
            logger.info("[视频号] 已选择链接类型「商品」")
            await page.wait_for_timeout(500)

            # ---- 步骤 3：点击「选择需要添加的商品」----
            r3 = await page.evaluate(
                f"""() => {{
                const shadow = {_WUJIE};
                if (!shadow) return 'no_shadow';
                const cw = shadow.querySelector(
                    'div.link-input-wrap div.post-component-choose-wrap div.content-wrap'
                );
                if (!cw) return 'no_content_wrap';
                cw.click();
                return 'ok';
            }}"""
            )
            if r3 != "ok":
                logger.warning("[视频号] 步骤7：点击 content-wrap 失败: %s", r3)
                return PublishResult(
                    success=False,
                    error_message="未找到「选择需要添加的商品」入口（content-wrap），无法挂载购物车",
                    failed_step="LinkSettingStep",
                )
            logger.info("[视频号] 已点击 content-wrap，等待商品弹窗")
        else:
            return PublishResult(
                success=False,
                error_message=f"打开商品弹窗异常: {direct_open}",
                failed_step="LinkSettingStep",
            )

        await page.wait_for_timeout(400)

        # ---- 等待弹窗可见 ----
        dialog_ok = False
        for _ in range(24):
            vis = await page.evaluate(_commodity_dialog_visible_fn())
            if vis:
                dialog_ok = True
                break
            await page.wait_for_timeout(250)
        if not dialog_ok:
            logger.warning("[视频号] 步骤7：add-commodity-dialog 未在预期时间内显示")
            return PublishResult(
                success=False,
                error_message="商品选择弹窗（add-commodity-dialog）未打开",
                failed_step="LinkSettingStep",
            )

        # ---- 步骤 4～5：填入搜索内容并点「筛选」----
        fill_r = await page.evaluate(
            f"""([text]) => {{
            const shadow = {_WUJIE};
            if (!shadow) return 'no_shadow';
            const dialog = shadow.querySelector('div.add-commodity-dialog');
            if (!dialog) return 'no_dialog';
            const input = dialog.querySelector('input[placeholder*="商品名称"]');
            if (!input) return 'no_input';
            input.focus();
            // 使用原生 setter 触发 React 受控输入状态更新，直接赋值 value 无效
            try {{
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(input, '');
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                nativeSetter.call(input, text);
            }} catch(e) {{
                input.value = '';
                input.value = text;
            }}
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
            const wrap = dialog.querySelector('div.search-btn');
            const btn = wrap ? wrap.querySelector('button') : null;
            if (!btn) return 'no_filter_btn';
            btn.click();
            return 'ok';
        }}""",
            [search_text],
        )
        if fill_r != "ok":
            logger.warning("[视频号] 步骤7：填搜索或点筛选失败: %s", fill_r)
            return PublishResult(
                success=False,
                error_message=f"弹窗内搜索/筛选失败: {fill_r}",
                failed_step="LinkSettingStep",
            )
        logger.info("[视频号] 已输入搜索内容并点击「筛选」")
        await page.wait_for_timeout(600)

        # ---- 步骤 6：等待表格有数据行 ----
        row_ready = False
        for _ in range(30):
            cnt = await page.evaluate(
                f"""() => {{
                const shadow = {_WUJIE};
                if (!shadow) return 0;
                const dialog = shadow.querySelector('div.add-commodity-dialog');
                if (!dialog) return 0;
                return dialog.querySelectorAll('.ant-table-tbody tr').length;
            }}"""
            )
            if cnt and int(cnt) > 0:
                row_ready = True
                break
            await page.wait_for_timeout(350)
        if not row_ready:
            logger.warning("[视频号] 步骤7：筛选后未出现商品行")
            return PublishResult(
                success=False,
                error_message="筛选后表格无商品行，请检查 goods_info 是否为有效商品名称/编码/链接",
                failed_step="LinkSettingStep",
            )

        # ---- 步骤 7：点击首行 ----
        sel_r = await page.evaluate(
            f"""() => {{
            const shadow = {_WUJIE};
            if (!shadow) return 'no_shadow';
            const dialog = shadow.querySelector('div.add-commodity-dialog');
            if (!dialog) return 'no_dialog';
            const row = dialog.querySelector('.ant-table-tbody tr');
            if (!row) return 'no_row';
            row.click();
            return 'ok';
        }}"""
        )
        if sel_r != "ok":
            logger.warning("[视频号] 步骤7：选中商品行失败: %s", sel_r)
            return PublishResult(
                success=False,
                error_message=f"无法选中商品行: {sel_r}",
                failed_step="LinkSettingStep",
            )
        logger.info("[视频号] 已点击表格首行选中商品")
        await page.wait_for_timeout(450)

        # ---- 步骤 8：点击已启用的「添加」----
        add_r = await page.evaluate(
            f"""() => {{
            const shadow = {_WUJIE};
            if (!shadow) return 'no_shadow';
            const dialog = shadow.querySelector('div.add-commodity-dialog');
            if (!dialog) return 'no_dialog';
            const buttons = dialog.querySelectorAll('button.weui-desktop-btn_primary');
            for (let i = 0; i < buttons.length; i++) {{
                const b = buttons[i];
                const t = (b.textContent || '').replace(/\\s+/g, ' ').trim();
                if (!t.startsWith('添加')) continue;
                if (b.disabled) continue;
                if (b.classList.contains('weui-desktop-btn_disabled')) continue;
                const st = window.getComputedStyle(b);
                if (st.display === 'none' || st.visibility === 'hidden') continue;
                b.click();
                return 'ok:' + t;
            }}
            return 'no_enabled_add';
        }}"""
        )
        if not str(add_r).startswith("ok"):
            logger.warning("[视频号] 步骤7：点击「添加」失败: %s", add_r)
            return PublishResult(
                success=False,
                error_message="添加按钮未就绪或未找到可点击的「添加」按钮（需先选中商品）",
                failed_step="LinkSettingStep",
            )
        logger.info("[视频号] 已点击「添加」(%s)", add_r)

        # ---- 步骤 9：等待弹窗关闭（display:none）----
        dialog_closed = False
        for _ in range(20):
            closed = await page.evaluate(
                f"""() => {{
                const shadow = {_WUJIE};
                if (!shadow) return true;
                const d = shadow.querySelector('div.add-commodity-dialog');
                if (!d) return true;
                const st = window.getComputedStyle(d);
                return st.display === 'none';
            }}"""
            )
            if closed:
                dialog_closed = True
                break
            await page.wait_for_timeout(300)

        if not dialog_closed:
            logger.warning("[视频号] 步骤7：商品弹窗在预期时间内未完全关闭，继续后续流程")

        # ---- 步骤 9 验证：链接区域应显示商品名称 ----
        await page.wait_for_timeout(300)
        verify_r = await page.evaluate(
            f"""() => {{
            const shadow = {_WUJIE};
            if (!shadow) return '';
            const wrap = shadow.querySelector('div.link-input-wrap');
            if (!wrap) return '';
            const t = (wrap.textContent || '').replace(/\\s+/g, ' ').trim();
            return (t && !t.includes('选择需要添加的商品')) ? t : '';
        }}"""
        )
        if verify_r:
            logger.info("[视频号] 步骤7：链接区域已显示商品内容：%s", verify_r[:50])
            USER_LOG.info("[视频号] 购物车商品已添加：%s", verify_r[:50])
        else:
            logger.warning("[视频号] 步骤7：弹窗已关闭但链接区域未检测到商品名称，请人工确认")
            USER_LOG.info("[视频号] 购物车挂载流程已执行（结果待确认）")

        logger.info("[视频号] 步骤7完成：购物车商品挂载流程已执行")
        return None
