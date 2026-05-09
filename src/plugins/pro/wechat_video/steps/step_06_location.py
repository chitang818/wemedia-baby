# -*- coding: utf-8 -*-
"""
步骤6：位置设置
文件路径: src/plugins/pro/wechat_video/steps/step_06_location.py

流程：
  - poi_info 有值：暂跳过（后续实现搜索位置功能）。
  - poi_info 为空：
      - metadata['wechat_empty_location_open_picker'] 为 False：本步直接完成（不点页面）。
      - 未设置该键（旧任务）或 True：在页面点开下拉并选「不显示位置」（原流程）。

字段依赖：metadata['poi_info']、metadata['wechat_empty_location_open_picker']（可选）

所有元素在 wujie-app Shadow DOM 内，需 JS 穿透访问。
"""
import logging
from typing import Dict, Any

from playwright.async_api import Page

from src.domain.publish.location_settings import effective_location_string_from_metadata
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors
from ..wujie_shadow import WUJIE_SHADOW_ROOT_JS as _WUJIE_SHADOW_JS

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class LocationSettingStep(BasePublishStep):
    """位置设置步骤。

    当任务中 poi_info 为空时：
    1. 点击位置下拉框
    2. 选择「不显示位置」
    3. 验证位置框显示「不显示位置」

    当 poi_info 有值时（后续实现搜索位置功能），暂跳过。
    """

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        location = effective_location_string_from_metadata(metadata)
        logger.info(f"[视频号] 步骤6：位置设置（位置='{location}'）")

        # 有位置信息时，位置搜索功能尚未实现，终止发布（避免带错误数据发布）
        if location:
            logger.error(f"[视频号] 检测到位置信息: {location}，但位置搜索功能尚未实现，终止发布")
            USER_LOG.error("[步骤6/11 位置设置] ✗ 任务配置了位置「%s」，但该功能尚未实现，终止发布", location)
            return PublishResult(
                success=False,
                error_message=f"位置搜索功能尚未实现（配置位置：{location}）",
                failed_step="步骤6/位置设置",
            )

        # 位置为空：由任务配置决定是否打开页面下拉选「不显示位置」；未配置（旧数据）保持原行为
        raw_flag = metadata.get("wechat_empty_location_open_picker")
        open_picker = True if raw_flag is None else bool(raw_flag)
        if not open_picker:
            logger.info("[视频号] 位置为空且配置为保留发布页默认位置，步骤6直接完成（不操作页面）")
            return None

        # ---- 位置为空：选择「不显示位置」 ----
        logger.info("[视频号] 位置为空，选择「不显示位置」")

        dropdown_sel = Selectors.PUBLISH.get("LOCATION_DROPDOWN", "")
        hide_option_sel = Selectors.PUBLISH.get("LOCATION_HIDE_OPTION", "")
        verify_sel = Selectors.PUBLISH.get("LOCATION_HIDE_VERIFY", "")

        # 1. 点击位置下拉框
        try:
            click_result = await page.evaluate(f"""() => {{
                const shadow = {_WUJIE_SHADOW_JS};
                if (!shadow) return 'no_shadow';
                const dropdown = shadow.querySelector('{dropdown_sel}');
                if (!dropdown) return 'dropdown_not_found';
                dropdown.click();
                return 'clicked';
            }}""")

            if click_result != 'clicked':
                logger.warning(f"[视频号] 点击位置下拉框失败: {click_result}，跳过位置设置")
                return None
            logger.info("[视频号] 已点击位置下拉框")
        except Exception as e:
            logger.warning(f"[视频号] 点击位置下拉框异常: {e}，跳过")
            return None

        await page.wait_for_timeout(500)

        # 2. 点击「不显示位置」
        try:
            hide_result = await page.evaluate(f"""() => {{
                const shadow = {_WUJIE_SHADOW_JS};
                if (!shadow) return 'no_shadow';
                // 查找包含「不显示位置」文本的选项
                const items = shadow.querySelectorAll('{hide_option_sel}');
                for (const item of items) {{
                    if (item.textContent.includes('不显示位置')) {{
                        item.click();
                        return 'clicked';
                    }}
                }}
                // 降级：查找 location-item 中的文本
                const allItems = shadow.querySelectorAll('div.location-item');
                for (const item of allItems) {{
                    if (item.textContent.includes('不显示位置')) {{
                        item.click();
                        return 'clicked_fallback';
                    }}
                }}
                return 'option_not_found';
            }}""")

            if hide_result and 'clicked' in hide_result:
                logger.info(f"[视频号] 已点击「不显示位置」({hide_result})")
            else:
                logger.warning(f"[视频号] 点击「不显示位置」失败: {hide_result}")
                return None
        except Exception as e:
            logger.warning(f"[视频号] 点击「不显示位置」异常: {e}")
            return None

        await page.wait_for_timeout(500)

        # 3. 验证位置框是否显示「不显示位置」
        try:
            verify_text = await page.evaluate(f"""() => {{
                const shadow = {_WUJIE_SHADOW_JS};
                if (!shadow) return '';
                const span = shadow.querySelector('{verify_sel}');
                return span ? span.textContent.trim() : '';
            }}""")

            if "不显示位置" in (verify_text or ""):
                logger.info("[视频号] 验证通过：位置已设为「不显示位置」")
            else:
                logger.warning(f"[视频号] 验证：位置框显示={verify_text}，可能未生效但继续执行")
        except Exception:
            pass

        logger.info("[视频号] 步骤6完成：位置设置成功")
        return None
