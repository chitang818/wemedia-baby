# -*- coding: utf-8 -*-
"""
步骤8D：声明原创
文件路径: src/plugins/pro/wechat_video/steps/step_08D_original.py

与《视频号_视频发布_DOM 分析报告_20260330》操作步骤 8 / wechat-channels-publish-analysis 3.3 一致：

  - is_original 为 False（或不存在）：跳过。
  - is_original 为 True：
      1. 若表单「声明原创」已勾选 → 直接成功（幂等）。
      2. 真实鼠标点击主区域原创可见勾选区 → 弹出「原创权益」弹窗。
      3. 真实鼠标勾选协议（优先 span.ant-checkbox，避免仅点隐藏 input 不写 Vue）。
      4. 真实鼠标点弹窗「声明原创」确认；协议未勾选则重试；确认后校验弹窗关闭。
      5. 成功判据：主区域复选框保持勾选且弹窗已关闭。

wujie + Vue/Ant Design 下 evaluate 内 el.click() 易导致假勾选，故关键步骤仅用 page.mouse.click。
"""
import json
import logging
from typing import Any, Dict, Optional, Tuple

from src.infrastructure.browser.automation_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors
from ..shadow_mouse import get_shadow_el_center, real_mouse_click_xy, shadow_eval_center
from ..wujie_shadow import WUJIE_SHADOW_ROOT_JS as _WUJIE_SHADOW_JS

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


def _truthy_is_original(val: Any) -> bool:
    """仅在为「明确为真」时返回 True；避免 JSON/表单里字符串 \"false\" 被 bool() 当成 True。"""
    if val is True:
        return True
    if val is False or val is None:
        return False
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("true", "1", "yes", "on"):
            return True
        return False
    return False


def _get_is_original(metadata: Dict[str, Any]) -> bool:
    """从 metadata 里解析是否声明原创。

    支持两种来源：
    1. 直接字段：metadata['is_original']（bool / 兼容字符串）
    2. 嵌套在 privacy_settings JSON 字符串或字典中：{"is_original": true}
    """
    direct: Optional[Any] = metadata.get("is_original")
    if direct is not None:
        return _truthy_is_original(direct)

    ps = metadata.get("privacy_settings")
    if ps:
        if isinstance(ps, str):
            try:
                ps = json.loads(ps)
            except Exception:
                ps = {}
        if isinstance(ps, dict) and "is_original" in ps:
            return _truthy_is_original(ps.get("is_original"))

    return False


async def wechat_main_original_checked(page: Page) -> Tuple[bool, str]:
    """只读：检测表单「声明原创」行是否已勾选（供发表步骤前预检与本步骤幂等）。"""
    try:
        r = await page.evaluate(
            f"""() => {{
            const shadow = {_WUJIE_SHADOW_JS};
            if (!shadow) return {{ checked: false, detail: 'no_shadow' }};
            const form = shadow.querySelector('.form');
            if (!form) return {{ checked: false, detail: 'no_form' }};
            for (const item of form.children) {{
                const t = item.textContent || '';
                if (!t.includes('声明原创')) continue;
                const input = item.querySelector('.ant-checkbox-input');
                const wrap = item.querySelector('span.ant-checkbox');
                const byInput = !!(input && input.checked);
                const byClass = !!(wrap && wrap.classList.contains('ant-checkbox-checked'));
                return {{ checked: byInput || byClass, detail: 'ok' }};
            }}
            return {{ checked: false, detail: 'no_declare_row' }};
        }}"""
        )
        if isinstance(r, dict):
            return bool(r.get("checked")), str(r.get("detail", ""))
    except Exception as e:
        return False, str(e)
    return False, "bad_result"


async def _dialog_agreement_checked(page: Page) -> Tuple[bool, str]:
    """只读：弹窗内「我已阅读并同意」是否已勾选。"""
    try:
        r = await page.evaluate(
            f"""() => {{
            const shadow = {_WUJIE_SHADOW_JS};
            if (!shadow) return {{ ok: false, detail: 'no_shadow' }};
            const dlg = shadow.querySelector('div.declare-original-dialog .weui-desktop-dialog')
                || shadow.querySelector('.declare-original-dialog');
            if (!dlg) return {{ ok: false, detail: 'no_dialog' }};
            const wrap = dlg.querySelector('.original-proto-wrapper');
            if (!wrap) return {{ ok: false, detail: 'no_proto_wrapper' }};
            const input = wrap.querySelector('.ant-checkbox-input');
            const span = wrap.querySelector('span.ant-checkbox');
            const byInput = !!(input && input.checked);
            const byClass = !!(span && span.classList.contains('ant-checkbox-checked'));
            return {{ ok: byInput || byClass, detail: 'ok' }};
        }}"""
        )
        if isinstance(r, dict):
            return bool(r.get("ok")), str(r.get("detail", ""))
    except Exception as e:
        return False, str(e)
    return False, "bad_result"


async def _dialog_visible_and_open(page: Page, dialog_sel: str) -> bool:
    """弹窗节点存在且可见（有布局尺寸）。"""
    try:
        ds = json.dumps(dialog_sel or "")
        return await page.evaluate(
            f"""() => {{
            const shadow = {_WUJIE_SHADOW_JS};
            if (!shadow) return false;
            const s = {ds};
            let d = (s && shadow.querySelector(s)) || shadow.querySelector('.declare-original-dialog');
            if (!d) return false;
            const st = window.getComputedStyle(d);
            if (st.display === 'none' || st.visibility === 'hidden') return false;
            const r = d.getBoundingClientRect();
            return r.width > 2 && r.height > 2;
        }}"""
        )
    except Exception:
        return False


class OriginalDeclareStep(BasePublishStep):
    """声明原创步骤（任务勾选 is_original 时执行，成功以主区域复选框勾选为准）。"""

    _DIALOG_WAIT_MS = 10000
    _DIALOG_POLL_MS = 250
    _POST_CONFIRM_VERIFY_MS = 8000
    _POST_CONFIRM_POLL_MS = 200

    async def _wait_original_rights_dialog(self, page: Page, dialog_sel: str) -> bool:
        """等待 Shadow 内「原创权益」弹窗（DOM 报告：标题/文案含「原创权益」）。"""
        deadline_ms = self._DIALOG_WAIT_MS
        elapsed = 0
        ds = json.dumps(dialog_sel or "")
        while elapsed < deadline_ms:
            try:
                found = await page.evaluate(
                    f"""() => {{
                    const shadow = {_WUJIE_SHADOW_JS};
                    if (!shadow) return false;
                    const sel = {ds};
                    let dlg = (sel && shadow.querySelector(sel)) || null;
                    if (dlg) {{
                        const tx = (dlg.innerText || '');
                        if (tx.includes('原创权益')) return true;
                    }}
                    dlg = shadow.querySelector('.declare-original-dialog');
                    if (dlg) {{
                        const tx = (dlg.innerText || '');
                        if (tx.includes('原创权益')) return true;
                    }}
                    return false;
                }}"""
                )
                if found:
                    return True
            except Exception as e:
                logger.debug("[视频号] 轮询原创权益弹窗异常: %s", e)
            await page.wait_for_timeout(self._DIALOG_POLL_MS)
            elapsed += self._DIALOG_POLL_MS
        return False

    async def _main_original_click_center(self, page: Page, main_checkbox_sel: str) -> Optional[Tuple[float, float]]:
        """主表单「声明原创」行：可见勾选区域中心坐标。"""
        xy = await shadow_eval_center(
            page,
            """
    const form = shadow.querySelector('.form');
    if (!form) return null;
    for (const item of form.children) {
        if (!(item.textContent || '').includes('声明原创')) continue;
        let el = item.querySelector('span.ant-checkbox');
        if (!el) el = item.querySelector('.ant-checkbox-inner');
        if (!el) el = item.querySelector('.ant-checkbox-wrapper');
        if (!el) return null;
        try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
        const r = el.getBoundingClientRect();
        if (r.width > 1 && r.height > 1) {
            return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
        }
    }
    return null;
""",
        )
        if xy:
            return xy
        if not (main_checkbox_sel or "").strip():
            return None
        s = json.dumps(main_checkbox_sel)
        return await shadow_eval_center(
            page,
            f"""
    const cb = shadow.querySelector({s});
    if (!cb) return null;
    let el = cb.closest('span.ant-checkbox');
    if (!el && cb.classList && cb.classList.contains('ant-checkbox-input')) {{
        const w = cb.closest('.ant-checkbox-wrapper') || cb.parentElement;
        if (w) el = w.querySelector('span.ant-checkbox') || w.querySelector('.ant-checkbox-inner');
    }}
    if (!el) el = cb;
    try {{ el.scrollIntoView({{ block: 'center', inline: 'nearest' }}); }} catch (e) {{}}
    const r = el.getBoundingClientRect();
    if (r.width > 1 && r.height > 1) {{
        return {{ x: r.left + r.width / 2, y: r.top + r.height / 2 }};
    }}
    return null;
""",
        )

    async def _agree_checkbox_click_center(
        self, page: Page, agree_checkbox_sel: str
    ) -> Optional[Tuple[float, float]]:
        """弹窗内协议：优先可见 ant-checkbox 区域。"""
        s_agree = json.dumps(agree_checkbox_sel or "")
        xy = await shadow_eval_center(
            page,
            f"""
    const dlg = shadow.querySelector('div.declare-original-dialog .weui-desktop-dialog')
        || shadow.querySelector('.declare-original-dialog');
    if (!dlg) return null;
    const agreeSel = {s_agree};
    let el = null;
    if (agreeSel) {{
        const hit = shadow.querySelector(agreeSel);
        if (hit && dlg.contains(hit)) {{
            el = hit.closest('span.ant-checkbox') || hit.parentElement?.querySelector('span.ant-checkbox');
            if (!el) el = hit.closest('.ant-checkbox-wrapper');
        }}
    }}
    if (!el) {{
        el = dlg.querySelector('.original-proto-wrapper span.ant-checkbox')
            || dlg.querySelector('.original-proto-wrapper .ant-checkbox-inner')
            || dlg.querySelector('.original-proto-wrapper .ant-checkbox-wrapper');
    }}
    if (!el) {{
        const candidates = dlg.querySelectorAll('.ant-checkbox-wrapper, label, span');
        for (const node of candidates) {{
            const tx = node.textContent || '';
            if (tx.includes('我已阅读') && tx.includes('同意')) {{
                const wrap = node.classList && node.classList.contains('ant-checkbox-wrapper')
                    ? node
                    : node.closest('.ant-checkbox-wrapper');
                const root = wrap || node;
                el = root.querySelector('span.ant-checkbox') || root.querySelector('.ant-checkbox-inner') || root;
                break;
            }}
        }}
    }}
    if (!el) {{
        // 兜底：整行协议区域中心（避免仅 checkbox 小图标被遮挡/动画中不可点）
        el = dlg.querySelector('.original-proto-wrapper');
    }}
    if (!el) return null;
    try {{ el.scrollIntoView({{ block: 'center', inline: 'nearest' }}); }} catch (e) {{}}
    const r = el.getBoundingClientRect();
    if (r.width > 1 && r.height > 1) {{
        return {{ x: r.left + r.width / 2, y: r.top + r.height / 2 }};
    }}
    return null;
""",
        )
        return xy

    async def _confirm_button_click_center(self, page: Page, confirm_btn_sel: str) -> Tuple[Optional[Tuple[float, float]], str]:
        """弹窗「声明原创」确认按钮中心；若禁用返回 reason。"""
        s_conf = json.dumps(confirm_btn_sel or "")
        r = await page.evaluate(
            f"""() => {{
            const shadow = {_WUJIE_SHADOW_JS};
            if (!shadow) return {{ xy: null, reason: 'no_shadow' }};
            let btn = shadow.querySelector({s_conf});
            if (!btn) {{
                const dlg = shadow.querySelector('div.declare-original-dialog .weui-desktop-dialog')
                    || shadow.querySelector('.declare-original-dialog');
                if (dlg) {{
                    for (const b of dlg.querySelectorAll('button')) {{
                        const tx = ((b.textContent || '').replace(/\\s+/g, '') || '').trim();
                        if (tx === '声明原创') {{
                            btn = b;
                            break;
                        }}
                    }}
                }}
            }}
            if (!btn) return {{ xy: null, reason: 'confirm_btn_not_found' }};
            if (btn.classList.contains('weui-desktop-btn_disabled')) {{
                return {{ xy: null, reason: 'btn_still_disabled' }};
            }}
            try {{ btn.scrollIntoView({{ block: 'center', inline: 'nearest' }}); }} catch (e) {{}}
            const rect = btn.getBoundingClientRect();
            if (rect.width > 1 && rect.height > 1) {{
                return {{
                    xy: {{ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }},
                    reason: 'ok',
                }};
            }}
            return {{ xy: null, reason: 'confirm_zero_size' }};
        }}"""
        )
        if not isinstance(r, dict):
            return None, "bad_eval"
        reason = str(r.get("reason", ""))
        xy_obj = r.get("xy")
        if isinstance(xy_obj, dict) and "x" in xy_obj and "y" in xy_obj:
            return (float(xy_obj["x"]), float(xy_obj["y"])), reason
        return None, reason

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        file_type = (metadata.get("file_type") or "video").lower()
        if file_type != "video":
            logger.info("[视频号] 非视频任务，跳过声明原创步骤（file_type=%s）", file_type)
            return None

        is_original = _get_is_original(metadata)
        logger.info("[视频号] 声明原创（is_original=%s）", is_original)
        USER_LOG.info(
            "%s ▶ 任务要求声明原创=%s",
            self._step_prefix(metadata, "声明原创"),
            "是" if is_original else "否",
        )

        if not is_original:
            logger.info("[视频号] 无需声明原创，跳过")
            USER_LOG.info("%s — 跳过（任务未勾选）", self._step_prefix(metadata, "声明原创"))
            return None

        main_checkbox_sel = Selectors.PUBLISH.get("ORIGINAL_CHECKBOX", "")
        dialog_sel = Selectors.PUBLISH.get("ORIGINAL_DIALOG", "")
        agree_checkbox_sel = Selectors.PUBLISH.get("ORIGINAL_DIALOG_AGREE_CHECKBOX", "")
        confirm_btn_sel = Selectors.PUBLISH.get("ORIGINAL_DIALOG_CONFIRM_BTN", "")

        checked, detail = await wechat_main_original_checked(page)
        if checked:
            logger.info("[视频号] 声明原创主复选框已勾选（%s），无需再操作", detail)
            USER_LOG.info("%s ✓ 已是勾选状态，跳过", self._step_prefix(metadata, "声明原创"))
            return None

        # ---- 1. 真实鼠标点击主区域「声明原创」----
        xy_main = await self._main_original_click_center(page, main_checkbox_sel)
        if not xy_main:
            xy_main = await get_shadow_el_center(page, main_checkbox_sel)
        if not xy_main or not await real_mouse_click_xy(page, xy_main):
            logger.error("[视频号] 无法对声明原创主区域执行真实点击（请避免遮挡浏览器窗口）")
            return PublishResult(
                success=False,
                error_message="无法点击声明原创复选框（未得到有效视口坐标或 mouse.click 失败），请勿遮挡窗口",
                failed_step="OriginalDeclareStep",
            )
        logger.info("[视频号] 已对主区域「声明原创」执行真实鼠标点击")
        USER_LOG.info("%s ▶ 已点击表单「声明原创」", self._step_prefix(metadata, "声明原创"))
        await page.wait_for_timeout(300)

        # ---- 2. 等待「原创权益」弹窗 ----
        has_dialog = await self._wait_original_rights_dialog(page, dialog_sel)
        if not has_dialog:
            checked2, _ = await wechat_main_original_checked(page)
            if checked2:
                logger.info("[视频号] 未检测到弹窗但主复选框已勾选，视为无弹窗流程成功")
                USER_LOG.info("%s ✓ 无弹窗流程，主复选框已勾选", self._step_prefix(metadata, "声明原创"))
                return None
            logger.error("[视频号] 「原创权益」弹窗未在 %sms 内出现且主复选框未勾选", self._DIALOG_WAIT_MS)
            return PublishResult(
                success=False,
                error_message="原创权益弹窗未出现，无法完成声明原创",
                failed_step="OriginalDeclareStep",
            )
        logger.info("[视频号] 「原创权益」弹窗已出现")
        USER_LOG.info("%s ▶ 已弹出「原创权益」窗口", self._step_prefix(metadata, "声明原创"))
        # 弹窗有入场动画，等待足够时间确保协议区域可点击（过早点击 getBoundingClientRect 返回0）
        await page.wait_for_timeout(600)

        # ---- 3. 勾选协议（真实鼠标 + 勾选校验）----
        for agree_attempt in range(1, 4):
            xy_ag = await self._agree_checkbox_click_center(page, agree_checkbox_sel)
            if not xy_ag:
                logger.warning("[视频号] 协议区域未得到可点击坐标 (attempt=%s)，等待后重试", agree_attempt)
                USER_LOG.info(
                    "%s 协议勾选定位失败，重试 %s/3",
                    self._step_prefix(metadata, "声明原创"),
                    agree_attempt,
                )
                await page.wait_for_timeout(500)
                continue
            if not await real_mouse_click_xy(page, xy_ag):
                logger.warning("[视频号] 协议区域真实点击失败 (attempt=%s)，重试", agree_attempt)
                USER_LOG.info(
                    "%s 协议点击失败，重试 %s/3",
                    self._step_prefix(metadata, "声明原创"),
                    agree_attempt,
                )
                await page.wait_for_timeout(500)
                continue
            await page.wait_for_timeout(400)
            ok_ag, det_ag = await _dialog_agreement_checked(page)
            if ok_ag:
                logger.info("[视频号] 协议已勾选（校验通过 %s）", det_ag)
                USER_LOG.info(
                    "%s 协议已勾选（第 %s 次）",
                    self._step_prefix(metadata, "声明原创"),
                    agree_attempt,
                )
                break
            logger.warning("[视频号] 协议勾选后仍未校验为已选 (attempt=%s, detail=%s)，重试点击", agree_attempt, det_ag)
        else:
            return PublishResult(
                success=False,
                error_message="「我已阅读并同意」勾选后校验仍失败，请检查页面或 DOM 是否变更",
                failed_step="OriginalDeclareStep",
            )
        USER_LOG.info("%s ▶ 已勾选「我已阅读并同意」", self._step_prefix(metadata, "声明原创"))

        # ---- 4. 点击「声明原创」确认（真实鼠标；禁用则再点协议）----
        confirm_ok = False
        for attempt in range(1, 5):
            xy_cf, cr = await self._confirm_button_click_center(page, confirm_btn_sel)
            if cr == "btn_still_disabled":
                logger.warning("[视频号] 确认按钮仍禁用，重试协议真实点击 (attempt=%s)", attempt)
                xy_ag = await self._agree_checkbox_click_center(page, agree_checkbox_sel)
                if xy_ag:
                    await real_mouse_click_xy(page, xy_ag)
                await page.wait_for_timeout(350)
                continue
            if cr != "ok" or not xy_cf:
                logger.error("[视频号] 无法得到确认按钮坐标: %s", cr)
                return PublishResult(
                    success=False,
                    error_message=f"无法点击弹窗「声明原创」确认: {cr}",
                    failed_step="OriginalDeclareStep",
                )
            if not await real_mouse_click_xy(page, xy_cf):
                logger.error("[视频号] 确认按钮真实点击失败")
                return PublishResult(
                    success=False,
                    error_message="点击弹窗「声明原创」确认失败（mouse.click），请勿遮挡窗口",
                    failed_step="OriginalDeclareStep",
                )
            confirm_ok = True
            logger.info("[视频号] 已对弹窗「声明原创」确认执行真实鼠标点击 (attempt=%s)", attempt)
            USER_LOG.info("%s ▶ 已点弹窗「声明原创」", self._step_prefix(metadata, "声明原创"))
            break

        if not confirm_ok:
            return PublishResult(
                success=False,
                error_message="声明原创确认按钮多次重试仍不可用",
                failed_step="OriginalDeclareStep",
            )

        # ---- 5. 主区勾选 + 弹窗关闭 ----
        verified = False
        elapsed = 0
        while elapsed < self._POST_CONFIRM_VERIFY_MS:
            checked3, det = await wechat_main_original_checked(page)
            dialog_open = await _dialog_visible_and_open(page, dialog_sel)
            if checked3 and not dialog_open:
                verified = True
                logger.info("[视频号] 验证通过：主复选框已勾选且弹窗已关闭 (%s)", det)
                break
            await page.wait_for_timeout(self._POST_CONFIRM_POLL_MS)
            elapsed += self._POST_CONFIRM_POLL_MS

        if not verified:
            checked3, det = await wechat_main_original_checked(page)
            dialog_open = await _dialog_visible_and_open(page, dialog_sel)
            if checked3 and dialog_open:
                logger.warning("[视频号] 主区已勾选但弹窗仍可见，尝试再次真实点击确认")
                xy_cf2, cr2 = await self._confirm_button_click_center(page, confirm_btn_sel)
                if cr2 == "ok" and xy_cf2 and await real_mouse_click_xy(page, xy_cf2):
                    await page.wait_for_timeout(600)
                for _ in range(20):
                    if not await _dialog_visible_and_open(page, dialog_sel):
                        if (await wechat_main_original_checked(page))[0]:
                            verified = True
                            break
                    await page.wait_for_timeout(200)

        if not verified:
            checked_final, det_f = await wechat_main_original_checked(page)
            still_dlg = await _dialog_visible_and_open(page, dialog_sel)
            logger.error(
                "[视频号] 声明原创收尾校验失败: main_checked=%s detail=%s dialog_open=%s",
                checked_final,
                det_f,
                still_dlg,
            )
            return PublishResult(
                success=False,
                error_message=(
                    "声明原创未完成：请确认主区域「声明原创」已勾选且「原创权益」弹窗已关闭；"
                    f"当前 main={checked_final}, dialog_open={still_dlg}"
                ),
                failed_step="OriginalDeclareStep",
            )

        USER_LOG.info("%s ✓ 完成（主复选框已勾选）", self._step_prefix(metadata, "声明原创"))
        logger.info("[视频号] 声明原创步骤完成")
        return None
