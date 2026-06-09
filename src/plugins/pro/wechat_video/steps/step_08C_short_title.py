# -*- coding: utf-8 -*-
"""
步骤8C：短标题填写
文件路径: src/plugins/pro/wechat_video/steps/step_08C_short_title.py

视频号发布页有一个「短标题」输入框，用于搜索和推荐展示。
对应发布任务中的 title 字段。若 title 为空则跳过，不为空则填写。
视频号要求：短标题最少 6 个字、最多 16 个字，不满足则无法通过发表校验。
除书名号、引号、冒号、加号、问号、百分号、摄氏度相关符号外，其它标点/符号会先替换为空格再计长。
该元素位于 wujie-app 的 Shadow DOM 内部。
"""
import logging
import re
import unicodedata
from typing import Dict, Any, Tuple

from src.infrastructure.browser.automation_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors
from ..wujie_shadow import WUJIE_SHADOW_ROOT_JS as _WUJIE_SHADOW_JS

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

# 短标题中除文字、数字、空白外，仅允许以下符号；其余标点/符号替换为空格（与视频号常见规范一致）
_ALLOWED_SHORT_TITLE_PUNCT = frozenset(
    {
        "《",
        "》",
        "「",
        "」",
        "『",
        "』",
        "'",
        '"',
        "\u2018",
        "\u2019",
        "\u201c",
        "\u201d",
        ":",
        "：",
        "+",
        "?",
        "？",
        "%",
        "\uff05",  # 全角百分号 ％
        "°",
        "℃",
    }
)


def _normalize_wechat_short_title(raw: str) -> Tuple[str, bool]:
    """将不允许的符号替换为空格并压缩空白。返回 (规范化后的文本, 是否与 strip(raw) 不同)。"""
    original_stripped = raw.strip()
    parts: list[str] = []
    for ch in raw:
        if ch.isspace():
            parts.append(" ")
            continue
        cat = unicodedata.category(ch)
        if cat[0] in ("L", "N"):
            parts.append(ch)
            continue
        if ch in _ALLOWED_SHORT_TITLE_PUNCT:
            parts.append(ch)
            continue
        parts.append(" ")
    merged = re.sub(r" +", " ", "".join(parts)).strip()
    return merged, merged != original_stripped


class ShortTitleStep(BasePublishStep):
    """短标题填写步骤。

    视频号发布页「短标题」输入框，对应任务中的 title 字段。
    - title 为空：跳过
    - title 不为空：聚焦输入框 → 清空 → 键盘输入 → 验证
    """

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        file_type = (metadata.get("file_type") or "video").lower()
        if file_type != "video":
            logger.info("[视频号] 非视频任务，跳过短标题步骤")
            return None

        # 对应发布任务中的 title 字段
        short_title = metadata.get("title", "") or ""
        logger.info(f"[视频号] 短标题设置（内容='{short_title}'）")

        # 无短标题，跳过
        if not short_title.strip():
            logger.info("[视频号] 未配置短标题（title 为空），跳过")
            return None

        short_title = short_title.strip()
        short_title, norm_changed = _normalize_wechat_short_title(short_title)
        if norm_changed:
            logger.info("[视频号] 短标题已去除不允许的符号并整理空白: '%s'", short_title)
            USER_LOG.info(
                "%s 已将无法使用的符号替换为空格并整理；规范化后: %s（%s 字）",
                self._step_prefix(metadata, "短标题"),
                short_title,
                len(short_title),
            )

        # 视频号短标题长度校验：至少 6 字、最多 16 字（规范化后计长），否则发表按钮无法通过
        if len(short_title) < 6:
            USER_LOG.warning(
                "%s 规范化后短标题不足 6 个字（当前 %s 字），不符合视频号要求",
                self._step_prefix(metadata, "短标题"),
                len(short_title),
            )
            return PublishResult(
                success=False,
                error_message=(
                    f"视频号短标题规范化后不足 6 个字（当前 {len(short_title)} 字）。"
                    f"仅允许书名号、引号、冒号、加号、问号、百分号、摄氏度符号等标点，其余符号已替换为空格；"
                    f"请保证有效内容 6～16 字后重试。"
                ),
                failed_step="ShortTitleStep",
            )
        if len(short_title) > 16:
            short_title = short_title[:16]
            logger.warning(f"[视频号] 短标题超过 16 字已截断为: '{short_title}'")
            USER_LOG.info("%s 已超过 16 字，从左保留前 16 字", self._step_prefix(metadata, "短标题"))
        logger.info(f"[视频号] 待填写短标题: '{short_title}'（{len(short_title)}字符）")

        # 获取选择器
        input_sel = Selectors.PUBLISH.get("SHORT_TITLE_INPUT", "")

        # 1. 聚焦短标题输入框
        try:
            focus_result = await page.evaluate(f"""() => {{
                const shadow = {_WUJIE_SHADOW_JS};
                if (!shadow) return 'no_shadow';
                const input = shadow.querySelector('{input_sel}');
                if (!input) return 'input_not_found';
                input.focus();
                input.click();
                return 'focused';
            }}""")

            if focus_result != 'focused':
                logger.warning(f"[视频号] 聚焦短标题输入框失败: {focus_result}")
                return PublishResult(
                    success=False,
                    error_message=f"未找到短标题输入框: {focus_result}",
                    failed_step="ShortTitleStep",
                )
            logger.info("[视频号] 已聚焦短标题输入框")
        except Exception as e:
            logger.error(f"[视频号] 聚焦短标题输入框异常: {e}")
            return PublishResult(
                success=False,
                error_message=f"聚焦短标题输入框异常: {e}",
                failed_step="ShortTitleStep",
            )

        await page.wait_for_timeout(200)

        # 2. 清空输入框原有内容
        try:
            await page.evaluate(f"""() => {{
                const shadow = {_WUJIE_SHADOW_JS};
                if (!shadow) return;
                const input = shadow.querySelector('{input_sel}');
                if (input) {{
                    input.focus();
                    input.value = '';
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
            }}""")
        except Exception as e:
            logger.debug("[视频号] 清空短标题输入框异常: %s", e)

        await page.wait_for_timeout(100)

        # 3. 通过键盘逐字输入（模拟真实打字，防风控）
        try:
            # 重新聚焦
            await page.evaluate(f"""() => {{
                const shadow = {_WUJIE_SHADOW_JS};
                if (!shadow) return;
                const input = shadow.querySelector('{input_sel}');
                if (input) input.focus();
            }}""")
            await page.wait_for_timeout(100)

            # 键盘输入
            await page.keyboard.type(short_title, delay=30)
            logger.info(f"[视频号] 已输入短标题（{len(short_title)}字符）")
        except Exception as e:
            logger.warning(f"[视频号] 键盘输入失败，尝试 JS 直接写入: {e}")
            # 降级：JS 直接赋值
            try:
                import json
                escaped = json.dumps(short_title)
                await page.evaluate(f"""() => {{
                    const shadow = {_WUJIE_SHADOW_JS};
                    if (!shadow) return;
                    const input = shadow.querySelector('{input_sel}');
                    if (input) {{
                        const setter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value'
                        ).set;
                        setter.call(input, {escaped});
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}""")
                logger.info("[视频号] 已通过 JS 直接写入短标题")
            except Exception as e2:
                logger.error(f"[视频号] JS 写入也失败: {e2}")
                return PublishResult(
                    success=False,
                    error_message=f"填写短标题失败: {e2}",
                    failed_step="ShortTitleStep",
                )

        # 4. 严格验证：读回 value，为空则视为填写失败，返回发布失败
        await page.wait_for_timeout(300)
        try:
            actual = await page.evaluate(f"""() => {{
                const shadow = {_WUJIE_SHADOW_JS};
                if (!shadow) return '';
                const input = shadow.querySelector('{input_sel}');
                return input ? input.value : '';
            }}""")

            if actual:
                logger.info(f"[视频号] 验证通过：短标题 = '{actual}'")
            else:
                logger.error("[视频号] 验证失败：短标题输入框 value 为空，终止发布")
                USER_LOG.error(
                    "%s ✗ 短标题写入验证失败（value 为空），终止发布",
                    self._step_prefix(metadata, "短标题"),
                )
                return PublishResult(
                    success=False,
                    error_message="短标题写入验证失败：input.value 为空",
                    failed_step="ShortTitleStep",
                )
        except Exception as e:
            logger.warning("[视频号] 验证短标题输入结果时异常: %s", e)

        logger.info("[视频号] 短标题步骤完成：填写成功")
        return None
