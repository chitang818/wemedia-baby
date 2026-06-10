# -*- coding: utf-8 -*-
"""
步骤10：发布设置（仅发布时间）
文件路径: src/plugins/community/kuaishou/steps/step_10_settings.py

流程：
  仅根据 metadata 的 scheduled_publish_time 设置「定时发布」或保持「立即发布」。
  不操作互动设置、不操作查看权限（保持页面默认，避免误改为好友可见/仅自己可见）。
"""
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from src.infrastructure.browser.automation_api import Page

from src.plugins.core.wait_helper import PluginWaitHelper
from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.utils.date_utils import format_schedule_time_st_str
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class PublishSettingsStep(BasePublishStep):
    """发布设置（仅发布时间：立即/定时，不操作互动与查看权限）。"""

    @staticmethod
    def _ymdhm_from_display(text: str) -> Optional[Tuple[int, int, int, int, int]]:
        """从输入框展示文案解析 (年, 月, 日, 时, 分)；无法解析返回 None。"""
        s = (text or "").strip()
        if not s:
            return None
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})", s)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)))
        m2 = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})", s)
        if m2:
            return (int(m2.group(1)), int(m2.group(2)), int(m2.group(3)), int(m2.group(4)), int(m2.group(5)))
        return None

    @staticmethod
    def _split_date_time(st_str: str) -> Tuple[str, str]:
        st_str = (st_str or "").strip()
        if " " in st_str:
            d, t = st_str.split(" ", 1)
            return d.strip(), t.strip()
        return st_str, ""

    @staticmethod
    def _with_random_seconds(st_str: str) -> str:
        """将 YYYY-MM-DD HH:mm 补成 YYYY-MM-DD HH:mm:00，若已含秒则原样返回。"""
        st_str = (st_str or "").strip()
        if not st_str:
            return ""
        # 已含秒
        try:
            datetime.strptime(st_str, "%Y-%m-%d %H:%M:%S")
            return st_str
        except Exception:
            pass
        # 补随机秒
        try:
            dt = datetime.strptime(st_str, "%Y-%m-%d %H:%M")
            return dt.replace(second=0).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return f"{st_str}:00"

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info("步骤10: 发布设置（互动/权限/发布时间）")
        _p = self._step_prefix(metadata, "发布设置")
        USER_LOG.info("%s ▶ 执行中", _p)
        config = metadata.get("anti_risk_config") or {}
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))

        # metadata 统一传入 scheduled_publish_time (YYYY-MM-DD HH:mm)；同时兼容 schedule_time
        schedule_time = metadata.get("scheduled_publish_time") or metadata.get("schedule_time")
        schedule_time = format_schedule_time_st_str(schedule_time) if schedule_time else ""
        schedule_time_with_seconds = self._with_random_seconds(schedule_time) if schedule_time else ""

        async def _human_click_locator(locator) -> None:
            # 优先 evaluate el.click()：与 DOM 文档推荐方式一致，对 button/div 均可靠；
            # 不调用 operation_delay，避免在时间选择器操作链中引入不必要的随机等待
            try:
                await locator.evaluate("el => el.click()")
                return
            except Exception:
                pass
            try:
                from src.infrastructure.anti_risk.human_like import human_click
                await human_click(page, locator, metadata, config, use_operation_delay=False)
            except Exception:
                await locator.click()

        async def _click_by_selector(selectors, *, must_be_visible: bool = True) -> bool:
            """按 selector 列表尝试点击，命中即返回 True。"""
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() == 0:
                        continue
                    if must_be_visible and not await loc.is_visible():
                        continue
                    try:
                        await loc.scroll_into_view_if_needed(timeout=8000)
                    except Exception:
                        pass
                    await _human_click_locator(loc)
                    return True
                except Exception:
                    continue
            return False

        async def _pause_poll() -> None:
            await self._await_pause(metadata)

        async def _wait_first_visible(selectors, timeout_ms: int) -> Optional[Any]:
            """等待任一 selector 可见，返回 locator；超时返回 None。"""
            matched_selector = await PluginWaitHelper.wait_for_any_visible(
                page,
                selectors,
                timeout_ms=timeout_ms,
                poll_interval_ms=int(200 * speed_rate),
                pause_callback=_pause_poll,
            )
            return page.locator(matched_selector).first if matched_selector else None

        async def _locate_visible_picker_ok_button() -> Optional[Any]:
            """在**当前可见**的日期时间弹层内查找「确定」按钮，避免旧节点或其它浮层误命中（DOM 文档 §10.3.4）。"""
            dropdowns = page.locator(".ant-picker-dropdown")
            try:
                n = await dropdowns.count()
            except Exception:
                n = 0
            for i in range(n):
                dd = dropdowns.nth(i)
                try:
                    if not await dd.is_visible():
                        continue
                except Exception:
                    continue
                try:
                    btn = dd.locator(".ant-picker-ok button").first
                    if await btn.count() > 0 and await btn.is_visible():
                        return btn
                except Exception:
                    pass
                try:
                    btn = dd.get_by_role("button", name="确定").first
                    if await btn.count() > 0 and await btn.is_visible():
                        return btn
                except Exception:
                    pass
            fallback_sels = list(Selectors.SETTINGS.get("PUBLISH_TIME_OK") or [".ant-picker-ok button"]) + [
                "#microSupport > div:nth-child(2) > div > div > div > div > div.ant-picker-footer > ul > li > button > span",
            ]
            return await _wait_first_visible(fallback_sels, timeout_ms=int(800 * speed_rate))

        async def _is_picker_dropdown_open() -> bool:
            """是否存在可见的时间选择弹层。"""
            dropdowns = page.locator(".ant-picker-dropdown")
            try:
                n = await dropdowns.count()
            except Exception:
                return False
            for i in range(n):
                try:
                    dd = dropdowns.nth(i)
                    if await dd.is_visible():
                        return True
                except Exception:
                    continue
            return False

        # 本步骤仅处理「发布时间」：不操作互动设置、不操作查看权限（保持页面默认，避免误改为好友可见/仅自己可见）

        # 发布设置位于页面最下方，先滚到页面底部再操作，避免元素未在视口内导致点击无效
        try:
            await page.evaluate(
                """() => {
                    const h = document.documentElement.scrollHeight || document.body.scrollHeight;
                    window.scrollTo(0, h);
                }"""
            )
            await page.wait_for_timeout(int(300 * speed_rate))
        except Exception:
            pass

        # --------------------------------------------
        # 发布时间（立即/定时）
        #    - 立即发布：页面默认即为立即发布，直接跳过
        #    - 定时发布：严格按用户提供 DOM 点击“定时发布”，填时间 input，点弹窗“确定”确认
        # --------------------------------------------
        if not schedule_time_with_seconds:
            logger.info("发布时间=立即发布（任务未设置 scheduled_publish_time），跳过页面操作")
            USER_LOG.info("%s ✓ 完成", _p)
            return None

        # 3.1 切到“定时发布” radio（仅限 #setting-tours 内发布时间区域，避免误点查看权限的 value=2=好友可见）
        schedule_radio_click_selectors = list(Selectors.SETTINGS.get("PUBLISH_SCHEDULE", []))
        if not schedule_radio_click_selectors:
            schedule_radio_click_selectors = [
                "#setting-tours div[class*='_publish-time_'] div.ant-radio-group label.ant-radio-wrapper:has(input[value='2'])",
            ]
        # 先把发布时间区域滚入视口，避免 antd 未渲染或点击被遮挡
        try:
            section = page.locator("#setting-tours [class*='_publish-time_'], [class*='_publish-time_']").first
            if await section.count() > 0:
                await section.scroll_into_view_if_needed(timeout=5000)
                await page.wait_for_timeout(int(200 * speed_rate))
        except Exception:
            pass

        dt_input_selectors = list(Selectors.SETTINGS.get("PUBLISH_TIME_INPUT", [])) + [
            ".ant-picker._data-picker_171ix_411 input",
            ".ant-picker input[placeholder*='选择日期时间']",
            "[class*='_publish-time_'] .ant-picker input",
        ]
        wait_after_click_ms = int(700 * speed_rate)
        dt_input = None
        for attempt in range(3):
            clicked_schedule = await _click_by_selector(schedule_radio_click_selectors, must_be_visible=False)
            if not clicked_schedule and attempt == 0:
                return PublishResult(success=False, error_message="未找到“定时发布”单选框（DOM 选择器未命中）")
            await page.wait_for_timeout(wait_after_click_ms)
            dt_input = await _wait_first_visible(dt_input_selectors, timeout_ms=10000)
            if dt_input:
                break
        if not dt_input:
            return PublishResult(success=False, error_message="已点击定时发布，但未出现“选择日期时间”输入框")

        try:
            await dt_input.scroll_into_view_if_needed(timeout=8000)
        except Exception:
            pass

        # 3.3 打开弹窗（antd dropdown），须出现可点的「确定」（文档 §10.3）
        dropdown_sel = (Selectors.SETTINGS.get("PUBLISH_TIME_DROPDOWN") or [".ant-picker-dropdown"])[0]

        picker_opened = False
        for open_try in range(1, 4):
            await dt_input.click()
            await page.wait_for_timeout(int(250 * speed_rate))
            probe_ok = await _locate_visible_picker_ok_button()
            if probe_ok:
                picker_opened = True
                logger.info("步骤10: 定时发布日期时间弹窗已打开（第 %s 次点击输入框）", open_try)
                USER_LOG.info(f"{_p} 定时发布：日期时间弹窗已打开（尝试 {open_try}/3）")
                break
            logger.warning("步骤10: 第 %s 次打开日期弹窗未看到「确定」按钮", open_try)
        if not picker_opened:
            return PublishResult(success=False, error_message="时间弹窗未打开或未出现“确定”按钮")

        # 3.4 写入值：AntD DatePicker 必须用真实键盘输入才能更新 React state，
        # JS evaluate 方式（即使触发 input/change 事件）无法进入 AntD 内部 model，
        # 导致点「确定」时 AntD 认为值未改变而拒绝关闭弹层。
        try:
            await dt_input.triple_click()
            await page.wait_for_timeout(int(100 * speed_rate))
        except Exception:
            try:
                await dt_input.click()
                await page.keyboard.press("Control+A")
            except Exception:
                pass
        await dt_input.type(schedule_time_with_seconds, delay=max(20, int(40 * speed_rate)))
        # 输入完成后稍作等待，让 AntD 内部 state 更新（识别出合法日期后「确定」才可点）
        await page.wait_for_timeout(int(400 * speed_rate))

        logger.info(
            "步骤10: 已写入定时时间输入框 value=%s，下一步必须点击弹层内「确定」方生效（文档 §10.3.4）",
            schedule_time_with_seconds,
        )
        USER_LOG.info(
            f"{_p} 定时发布：已填入 {schedule_time_with_seconds}，需点击弹窗「确定」提交"
        )
        await page.wait_for_timeout(int(200 * speed_rate))

        # 3.5 点击弹窗「确定」：写入后须重新定位按钮（AntD 可能刷新节点）；支持多次点击直至弹层关闭
        max_ok_attempts = 3
        confirm_clicked = False
        for attempt in range(1, max_ok_attempts + 1):
            ok_btn = await _locate_visible_picker_ok_button()
            if not ok_btn:
                # 找不到「确定」按钮时，先判断弹层是否已经关闭——
                # AntD 淡出动画期间弹层仍在 DOM 但「确定」按钮可能已消失，
                # 若弹层本身也已关闭说明上一次点击已成功，直接退出循环。
                if not await _is_picker_dropdown_open():
                    logger.info("步骤10: 未找到「确定」按钮且弹层已关闭，视为点击成功")
                    USER_LOG.info("%s 定时发布：弹窗已关闭，定时时间已提交", _p)
                    confirm_clicked = True
                    break
                logger.warning("步骤10: 第 %s 次未定位到「确定」，尝试再次点击输入框打开弹窗", attempt)
                USER_LOG.info(
                    f"{_p} 定时发布：未定位到「确定」按钮，重新点击日期输入框（{attempt}/{max_ok_attempts}）"
                )
                await dt_input.click()
                await page.wait_for_timeout(int(300 * speed_rate))
                ok_btn = await _locate_visible_picker_ok_button()
            if not ok_btn:
                continue

            logger.info(
                "步骤10: 点击定时选择器弹窗「确定」button（第 %s/%s 次，目标时间=%s）",
                attempt,
                max_ok_attempts,
                schedule_time_with_seconds,
            )
            USER_LOG.info(
                f"{_p} 定时发布：正在点击弹窗「确定」提交（第 {attempt}/{max_ok_attempts} 次）"
            )
            try:
                await ok_btn.scroll_into_view_if_needed(timeout=8000)
            except Exception:
                pass
            try:
                await _human_click_locator(ok_btn)
                confirm_clicked = True
            except Exception:
                try:
                    box = await ok_btn.bounding_box()
                    if box:
                        await page.mouse.click(
                            box["x"] + box["width"] / 2,
                            box["y"] + box["height"] / 2,
                        )
                        confirm_clicked = True
                except Exception:
                    logger.exception("步骤10: 点击「确定」失败（人机/坐标均失败）")

            # AntD 弹层淡出动画约需 400-500ms，需足够等待后再判断是否已关闭，
            # 等待太短（350ms）会误判为"弹层仍在"，导致下次循环又把弹层打开。
            await page.wait_for_timeout(int(900 * speed_rate))
            if not await _is_picker_dropdown_open():
                logger.info("步骤10: 「确定」已生效，.ant-picker-dropdown 弹层已关闭")
                USER_LOG.info("%s 定时发布：已点击「确定」，日期时间弹窗已关闭", _p)
                break

            logger.warning("步骤10: 点击「确定」后日期弹层仍可见，将重试（第 %s 次）", attempt)
            USER_LOG.warning(
                f"{_p} 定时发布：点击「确定」后弹窗仍在，重试（{attempt}/{max_ok_attempts}）"
            )
            # 等弹层彻底关闭或超时后，再重新点击输入框重新触发弹窗，避免旧弹层状态干扰下一轮
            for _ in range(20):
                await page.wait_for_timeout(int(200 * speed_rate))
                if not await _is_picker_dropdown_open():
                    break
            # 重新输入时间，确保 AntD state 里有最新值
            try:
                await dt_input.triple_click()
                await page.wait_for_timeout(int(100 * speed_rate))
                await dt_input.type(schedule_time_with_seconds, delay=max(20, int(40 * speed_rate)))
                await page.wait_for_timeout(int(400 * speed_rate))
            except Exception as reenter_e:
                logger.debug("步骤10: 重试前重新输入时间失败（将继续）: %s", reenter_e)
        else:
            return PublishResult(
                success=False,
                error_message="定时发布失败：多次点击弹窗「确定」后日期时间弹层仍未关闭，时间可能未提交到页面",
            )

        if not confirm_clicked:
            logger.info("步骤10: 弹层已关闭但未记录到点击回调成功，继续以输入框校验为准")

        # 兼容：等待首个 dropdown 隐藏或短暂 settle（多弹层时以上已用「是否仍有可见弹层」判断）
        dropdown = page.locator(dropdown_sel).first
        try:
            await dropdown.wait_for(state="hidden", timeout=5000)
        except Exception:
            try:
                await page.wait_for_timeout(int(250 * speed_rate))
            except Exception:
                pass

        # 3.6 校验：非空 + 展示时间与任务年月日时分一致（防 JS 改 value 未进 AntD model）
        try:
            final_val = await dt_input.input_value()
        except Exception:
            final_val = ""
        if not final_val:
            return PublishResult(success=False, error_message="定时发布设置失败：时间输入框未写入成功")

        exp = self._ymdhm_from_display(schedule_time)
        got = self._ymdhm_from_display(final_val)
        if got is None:
            return PublishResult(
                success=False,
                error_message=(
                    f"定时发布后无法从输入框解析时间（展示为 {final_val!r}），请核对页面格式是否变更"
                ),
            )
        if exp is not None and got != exp:
            return PublishResult(
                success=False,
                error_message=(
                    f"定时发布展示与任务不一致：任务要求 {schedule_time}，页面为 {final_val!r}（解析年月日时分 {got} vs 期望 {exp}）"
                ),
            )

        USER_LOG.info(f"{_p} ✓ 已设置定时发布: {final_val}")
        return None
