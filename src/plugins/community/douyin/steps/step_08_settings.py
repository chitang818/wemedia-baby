# -*- coding: utf-8 -*-
"""
步骤8：发布设置
文件路径: src/plugins/community/douyin/steps/step_08_settings.py

流程（依次执行）：
  1. 页面滚动到底部暴露设置区
  2. 可见性设置：根据 privacy 字段选择“公开”、“好友可见”或“私密”（兜底选项）
  3. 保存权限：根据 allow_download 设置“允许保存”或“不允许保存”
  4. 发布时间：
     - 若 schedule_time 为空，则选择“立即发布”
     - 若有定时时间，先点击“定时发布”单选按钮，再在时间输入框内分段逐个修正输入时间，
       匹配目标时间格式 YYYY-MM-DD HH:mm，保证输入合法防风控。

字段依赖：
  - metadata['privacy_settings']: 包含 privacy ("public"/"friend"/"private") 和 allow_download (bool)
  - metadata['schedule_time']: 若传入则触发定时发布
"""
import logging
import json
import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from playwright.async_api import Page

from src.plugins.core.wait_helper import PluginWaitHelper
from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.community.douyin.selectors import Selectors
from src.utils.date_utils import format_schedule_time_st_str
from ._base import BasePublishStep, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class PublishSettingsStep(BasePublishStep):
    """
    发布设置（权限、可见性、定时发布等）。
    """

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)
        input_delay = max(10, int(20 * speed_rate))
        config = metadata.get("anti_risk_config") or {}

        logger.info("===== 发布设置 =====")
        # 发布设置与发布按钮在页面最下部，先滚动到底部确保在可视范围内
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(300)
        except Exception as e:
            logger.debug(f"步骤8 滚动到底部异常: {e}")

        from src.infrastructure.anti_risk.human_like import human_click
        from src.infrastructure.anti_risk.delays import random_delay

        # ---------------------------------------------------------
        # 1. 谁可以看 (可见性设置)
        # ---------------------------------------------------------
        privacy_settings = metadata.get("privacy_settings", {})
        if isinstance(privacy_settings, str):
            try:
                privacy_settings = json.loads(privacy_settings)
            except Exception:
                privacy_settings = {}
                
        privacy = privacy_settings.get("privacy", "public")
        
        try:
            privacy_selector = Selectors.SETTINGS.get("PRIVACY_PUBLIC", [])
            if privacy == "friend":
                privacy_selector = Selectors.SETTINGS.get("PRIVACY_FRIEND", [])
            elif privacy == "private" or privacy == "fans":
                # 没有粉丝可见的话就选私密兜底
                privacy_selector = Selectors.SETTINGS.get("PRIVACY_PRIVATE", [])

            clicked = await self._check_radio_option(
                page, privacy_selector, metadata, config, wait_ms
            )
            if clicked:
                await random_delay(page, wait_ms(200), metadata, config)
                # 与「立即发布」一致：用 native input 再校验，避免点在过宽 label 上误选好友可见
                verify_sel = {
                    "public": "label.radio-d4zkru:has-text('公开') input.radio-native-p6VBGt",
                    "friend": "label.radio-d4zkru:has-text('好友可见') input.radio-native-p6VBGt",
                    "private": "label.radio-d4zkru:has-text('仅自己可见') input.radio-native-p6VBGt",
                    "fans": "label.radio-d4zkru:has-text('仅自己可见') input.radio-native-p6VBGt",
                }.get(privacy, "label.radio-d4zkru:has-text('公开') input.radio-native-p6VBGt")
                v = page.locator(verify_sel).first
                verified = True
                if await v.count() > 0:
                    try:
                        if not await v.is_checked():
                            await v.check(force=True)
                            await random_delay(page, wait_ms(200), metadata, config)
                        verified = await v.is_checked()
                        if not verified:
                            logger.warning("谁可以看：目标单选未处于选中状态，可能存在误点或页面结构变化")
                    except Exception as e:
                        verified = False
                        logger.debug(f"可见性选中校验/重试: {e}")
                if verified:
                    USER_LOG.info(f"[步骤8/9 发布设置] ▶ 已设置可见性: {privacy}")
                else:
                    USER_LOG.warning(
                        f"[步骤8/9 发布设置] ▶ 可见性可能未生效（期望 {privacy}），请人工核对页面「谁可以看」"
                    )
            if not clicked:
                logger.warning(f"无法找到对应的谁可以看选项: {privacy}")
        except Exception as e:
            logger.warning(f"设置可见性异常: {e}")

        # ---------------------------------------------------------
        # 2. 保存权限 
        # ---------------------------------------------------------
        allow_download = privacy_settings.get("allow_download", True)
        
        try:
            save_selector = (
                Selectors.SETTINGS.get("SAVE_ALLOW", [])
                if allow_download
                else Selectors.SETTINGS.get("SAVE_DISALLOW", [])
            )
            clicked = await self._check_radio_option(
                page, save_selector, metadata, config, wait_ms
            )
            if clicked:
                await random_delay(page, wait_ms(400), metadata, config)
                USER_LOG.info(f"[步骤8/9 发布设置] ▶ 已设置保存权限: {allow_download}")
            if not clicked:
                logger.warning(f"无法找到对应的保存权限选项: {allow_download}")
        except Exception as e:
            logger.warning(f"设置保存权限异常: {e}")

        # ---------------------------------------------------------
        # 3. 发布时间 (立即/定时)
        # ---------------------------------------------------------
        # metadata 里叫 schedule_time 还是 scheduled_publish_time?
        # 取决于之前从 repository 或者 ui 页面传过来的 key。在 ui 里是 scheduled_publish_time 进库。
        # 这里兼容两者，取一个有效的。
        schedule_time = metadata.get("scheduled_publish_time") or metadata.get("schedule_time")
        
        try:
            if not schedule_time:
                # 立即发布：与「定时发布」分支一致，对 input 使用 check()，避免 human_click 点在过宽的 label 上误选定时
                now_selector = Selectors.SETTINGS.get("PUBLISH_NOW", [])
                clicked = False
                for sel in now_selector:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() == 0:
                            continue
                        tag = await loc.evaluate("el => el.tagName && el.tagName.toLowerCase()")
                        is_input = tag == "input"
                        # input 元素（radio/checkbox）通常隐藏，跳过 is_visible 检查
                        if not is_input and not await loc.is_visible():
                            continue
                        await loc.scroll_into_view_if_needed()
                        await random_delay(page, wait_ms(200), metadata, config)
                        if is_input:
                            await loc.check(force=True)
                        else:
                            try:
                                await human_click(page, loc, metadata, config)
                            except Exception:
                                await loc.click(force=True)
                        clicked = True
                        await random_delay(page, wait_ms(400), metadata, config)
                        break
                    except Exception:
                        continue
                # 用文案作用域内的 native radio 再校验一次，避免误点后仍以为成功
                verify_inp = page.locator(
                    "label.radio-d4zkru:has-text('立即发布') input.radio-native-p6VBGt"
                ).first
                if await verify_inp.count() > 0:
                    try:
                        if not await verify_inp.is_checked():
                            await verify_inp.check(force=True)
                            await random_delay(page, wait_ms(200), metadata, config)
                        if not await verify_inp.is_checked():
                            logger.warning("立即发布单选未处于选中状态，页面可能仍为定时发布")
                    except Exception as e:
                        logger.debug(f"立即发布选中校验/重试: {e}")
                if clicked:
                    logger.info("已选择立即发布")
            else:
                # 定时发布：必须先选中「定时发布」单选，时间输入框才会出现；且定时时间必须设置成功后才能进入步骤9
                st_str = format_schedule_time_st_str(schedule_time) or ""
                logger.info(f"检测到定时发布时间: {st_str}，尝试设置")
                USER_LOG.info(f"[步骤8/9 发布设置] ▶ 尝试设置定时: {st_str}")
                schedule_selector_list = Selectors.SETTINGS.get("PUBLISH_SCHEDULE", [])
                sel_for_debug = (schedule_selector_list[0] if schedule_selector_list else "")

                # 勾选「定时发布」：
                # 视频页 = radio-native-p6VBGt (hidden input)，图文页 = checkbox (hidden input)
                # native input 的 is_visible() 通常返回 false，需要额外降级到父 label 可见性判断
                try:
                    clicked = False
                    for sel in schedule_selector_list:
                        try:
                            loc = page.locator(sel).first
                            if await loc.count() == 0:
                                continue
                            tag = await loc.evaluate("el => el.tagName && el.tagName.toLowerCase()")
                            is_input = tag == "input"
                            # input 元素通常隐藏，跳过 is_visible 检查；label/其他元素仍需可见
                            if not is_input and not await loc.is_visible():
                                continue
                            await loc.scroll_into_view_if_needed()
                            await random_delay(page, wait_ms(150), metadata, config)
                            if is_input:
                                await loc.check(force=True)
                            else:
                                try:
                                    await human_click(page, loc, metadata, config)
                                except Exception:
                                    await loc.click(force=True)
                            clicked = True
                            await random_delay(page, wait_ms(400), metadata, config)
                            break
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug(f"定时发布 checkbox 未命中或不可见: {sel_for_debug}, {e}")
                    clicked = False

                if not clicked:
                    logger.warning("未找到定时发布选项（视频页 radio / 图文页 checkbox），可能页面结构变化")
                    USER_LOG.warning("[步骤8/9 发布设置] ✗ 未选中定时发布，无法设置时间")
                    return PublishResult(success=False, error_message="未找到定时发布按钮，定时发布必须设置成功后才能继续", failed_step="PublishSettingsStep")

                # 选中「定时发布」后，等待时间输入框出现（优先主选择器，延长等待避免首次未渲染）
                schedule_input_selectors = [
                    "input[format='yyyy-MM-dd HH:mm']",
                    ".semi-datepicker-input input",
                    "input.semi-input[placeholder='日期和时间']",
                    "input[placeholder*='日期和时间']",
                    "input[placeholder*='发布时间']",
                    "input[class*='date-picker']",
                ]
                matched_input_selector = await PluginWaitHelper.wait_for_any_visible(
                    page,
                    schedule_input_selectors,
                    timeout_ms=8000,
                    poll_interval_ms=250,
                    pause_callback=lambda: self._await_pause(metadata),
                )
                inp = page.locator(matched_input_selector).first if matched_input_selector else None
                if inp is None:
                    logger.warning("选中定时发布后，定时时间输入框未在 8 秒内出现")
                    USER_LOG.warning("[步骤8/9 发布设置] ✗ 时间输入框未出现")
                    return PublishResult(success=False, error_message="选中定时发布后未出现时间输入框，定时时间必须设置成功后才能继续", failed_step="PublishSettingsStep")

                # 解析目标时间（st_str 已在上面格式化为 YYYY-MM-DD HH:mm）
                parsed = self._parse_schedule_time(st_str)
                if not parsed:
                    logger.warning(f"无法解析定时时间: {st_str}")
                    USER_LOG.warning("[步骤8/9 发布设置] ✗ 时间格式无效")
                    return PublishResult(success=False, error_message="定时时间格式无效，定时发布必须设置成功后才能继续", failed_step="PublishSettingsStep")

                year, month, day, hour, minute = parsed
                logger.info(f"找到定时发布时间输入框，采用分段输入设置时间")
                try:
                    await human_click(page, inp, metadata, config)
                except Exception:
                    await inp.click()
                await random_delay(page, wait_ms(300), metadata, config)
                current = await inp.input_value()
                filled = False
                if not current or len(current) != 16 or not re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", current):
                    try:
                        await inp.fill(st_str)
                        filled = (await inp.input_value()) == st_str
                    except Exception as e:
                        logger.warning(f"时间输入框当前值格式异常且 fill 失败: {e}")
                    if not filled:
                        logger.warning("定时时间输入框格式异常，无法分段输入")
                else:
                    filled = await self._set_schedule_time_by_segments(
                        page, inp, st_str, (year, month, day, hour, minute), wait_ms, metadata, config
                    )

                if not filled:
                    logger.warning("定时时间设置失败，不进入步骤9")
                    USER_LOG.warning("[步骤8/9 发布设置] ✗ 未找到时间输入框或设置异常")
                    return PublishResult(success=False, error_message="定时发布时间设置失败，定时发布必须设置成功后才能继续", failed_step="PublishSettingsStep")
                await random_delay(page, wait_ms(300), metadata, config)
                logger.info(f"已设置定时时间: {st_str}")
                USER_LOG.info(f"[步骤8/9 发布设置] ▶ 已设置定时: {st_str}")

        except Exception as e:
            logger.warning(f"定时/立即发布设置异常: {e}")
            USER_LOG.warning("[步骤8/9 发布设置] ✗ 时间设置异常（不阻断）")
            schedule_time = metadata.get("scheduled_publish_time") or metadata.get("schedule_time")
            if schedule_time:
                return PublishResult(success=False, error_message=f"定时发布设置异常: {e}，定时时间必须设置成功后才能继续", failed_step="PublishSettingsStep")

        return None

    async def _check_radio_option(
        self,
        page: Page,
        selector_list,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms,
    ) -> bool:
        """对发布设置区的 Semi 单选：优先勾选 label 内 native input，避免点在过宽 label 上误选相邻项。"""
        from src.infrastructure.anti_risk.human_like import human_click
        from src.infrastructure.anti_risk.delays import random_delay

        for sel in selector_list:
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue
                tag = await loc.evaluate("el => el.tagName && el.tagName.toLowerCase()")
                if tag != "input" and not await loc.is_visible():
                    continue
                await loc.scroll_into_view_if_needed()
                await random_delay(page, wait_ms(200), metadata, config)
                if tag == "input":
                    await loc.check(force=True)
                else:
                    try:
                        await human_click(page, loc, metadata, config)
                    except Exception:
                        await loc.click()
                return True
            except Exception:
                continue
        return False

    def _parse_schedule_time(self, st_str: str) -> Optional[Tuple[int, int, int, int, int]]:
        """解析 'YYYY-MM-DD HH:mm' 为 (year, month, day, hour, minute)。"""
        try:
            dt = datetime.strptime(st_str.strip(), "%Y-%m-%d %H:%M")
            return (dt.year, dt.month, dt.day, dt.hour, dt.minute)
        except Exception:
            return None

    async def _set_schedule_time_by_segments(
        self,
        page: Page,
        inp: Any,
        st_str: str,
        parsed: Tuple[int, int, int, int, int],
        wait_ms,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        """在时间输入框内按年/月/日/时/分五段分别比对，不同则选中→删除→输入；最后读回值与 st_str 一致才返回 True。"""
        from src.infrastructure.anti_risk.delays import random_delay

        # st_str 格式 "YYYY-MM-DD HH:mm" 共 16 字符，索引 11-12 为时、14-15 为分，中间 13 为冒号不可覆盖
        year, month, day, hour, minute = parsed
        segments = [
            (0, 4, f"{year:04d}"),
            (5, 7, f"{month:02d}"),
            (8, 10, f"{day:02d}"),
            (11, 13, f"{hour:02d}"),   # 时：仅两位数字，不包含冒号
            (14, 16, f"{minute:02d}"), # 分：仅两位数字
        ]
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        type_delay = max(10, int(30 * speed_rate))

        try:
            current = await inp.input_value()
            if len(current) != 16 or not re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", current):
                return False
            for start, end, target_str in segments:
                if current[start:end] == target_str:
                    continue
                await inp.evaluate(
                    "(el, [s, e]) => { el.focus(); el.setSelectionRange(s, e); }",
                    [start, end],
                )
                await page.keyboard.press("Backspace")
                await page.keyboard.type(target_str, delay=type_delay)
                await random_delay(page, wait_ms(30), metadata, config)
                current = await inp.input_value()
                if len(current) != 16:
                    logger.warning("分段输入后输入框长度异常")
                    return False
            return (await inp.input_value()) == st_str
        except Exception as e:
            logger.warning(f"定时时间分段输入异常: {e}")
            return False
