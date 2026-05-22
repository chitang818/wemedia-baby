# -*- coding: utf-8 -*-
"""
步骤4：作品描述（标题与简介）
文件路径: src/plugins/community/douyin/steps/step_04_description.py

流程：
  1. 标题填写：尽力找到标题区（TITLE_INPUT；视频「填写作品获得…」/ 图文「添加作品标题」），使用拟人输入或 Clipboard+Backspace 兜底。
  2. 作品简介（包含标题兜底和 #话题）：
     - 预处理：用全站统一的 `topics.parse_topic_list` 解析本任务 description，打出话题个数与列表；并与 metadata.tags 对比。
       便于区分：解析数为 0/偏少 → 查 `domain.publish.work_description`；解析正确但页面话题不全 → 查本步骤输入逻辑。
     - 定位到 contenteditable 输入框（DESC_EDITOR；视频「添加作品简介」/ 图文「添加作品描述...」与 editor-comp-publish）
     - 拟人点击并聚焦，全选并清空旧内容
     - 对含紧邻「#话题#话题」的文案：先规范化在非空白后紧跟的 `#` 前补空格；
       仍全程用逐字 type（delay 随 speed_rate），多话题时在「空格+#」分段边界插入 random_delay，模拟手动打完一段再打下一段，并给话题芯片留出形成时间（不做一次性粘贴/insert_text，与防风控一致）。
     - 若末尾为 #关键词（检测正则结尾），则自动补充按下 'Space' 空格键，以触发抖音自带的话题识别与收录确认。

字段依赖：
  - metadata['title']: 标题
  - metadata['description']: 描述文本（通常包含前置拼接好的话题）
  - metadata['tags']: 此部分直接与描述一起发送
  - metadata['speed_rate']: 打字速度与操作停顿等影响系数
"""
import logging
import re
from typing import Any, Callable, Dict, List
from playwright.async_api import Page

from src.domain.publish.work_description import parse_topic_list
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

_TOPIC_PREVIEW_MAX = 12


def _normalize_meta_tag_entries(tags: List[str]) -> List[str]:
    """与 parse_topic_list 输出可比：去空白、去前导井号（含全角）。"""
    out: List[str] = []
    for t in tags:
        if t is None:
            continue
        s = str(t).strip().replace("\uff03", "").lstrip("#").strip()
        if s:
            out.append(s)
    return out


def _format_topics_for_log(topics: List[str]) -> str:
    if not topics:
        return "（无）"
    head = topics[:_TOPIC_PREVIEW_MAX]
    s = "、".join(head)
    if len(topics) > _TOPIC_PREVIEW_MAX:
        s += f" …共{len(topics)}个"
    return s


def _log_description_topic_preprocess(description: str, tags_meta: List[str]) -> List[str]:
    """发布侧描述步骤专用：按全站规则解析文案内话题并打日志，便于定位解析层 vs 输入层问题。"""
    raw = description or ""
    parsed = parse_topic_list(raw)
    meta_norm = _normalize_meta_tag_entries(tags_meta)

    logger.info(
        "【描述预处理】从本任务作品描述解析到 %d 个话题（规则同 topics.parse_topic_list）：%s",
        len(parsed),
        parsed,
    )
    logger.info(
        "【描述预处理】metadata.tags 共 %d 项（去井号后）=%s",
        len(meta_norm),
        meta_norm,
    )

    if len(parsed) != len(meta_norm):
        logger.warning(
            "【描述预处理】文案解析话题数(%d) 与 metadata.tags 项数(%d) 不一致，请核对批量/文案库是否把描述与 tags 同步下发",
            len(parsed),
            len(meta_norm),
        )
    else:
        if parsed and meta_norm and set(parsed) != set(meta_norm):
            logger.warning(
                "【描述预处理】话题数量一致但词条集合不同：文案=%s tags=%s",
                parsed,
                meta_norm,
            )

    USER_LOG.info(
        "[步骤4/9 作品描述] ▶ 预处理：从文案解析到 %d 个话题「%s」",
        len(parsed),
        _format_topics_for_log(parsed),
    )
    if meta_norm:
        USER_LOG.info(
            "[步骤4/9 作品描述] ▶ 预处理：任务携带 tags %d 项「%s」",
            len(meta_norm),
            _format_topics_for_log(meta_norm),
        )
    else:
        USER_LOG.info(
            "[步骤4/9 作品描述] ▶ 预处理：任务未单独携带 tags（仅以文案为准）"
        )
    if len(parsed) != len(meta_norm):
        USER_LOG.warning(
            "[步骤4/9 作品描述] ⚠ 文案解析话题数(%d) 与 tags 项数(%d) 不一致，请查任务配置/文案库",
            len(parsed),
            len(meta_norm),
        )

    return parsed


def _title_selectors_for(metadata: Dict[str, Any]) -> list:
    """按发布类型排序：图文页优先匹配「添加作品标题」相关选择器。"""
    base = list(Selectors.PUBLISH.get("TITLE_INPUT") or [])
    if (metadata.get("file_type") or "video").lower() != "image":
        return base
    pref = [s for s in base if "添加作品标题" in s]
    rest = [s for s in base if s not in pref]
    return pref + rest


def _normalize_douyin_topic_spacing(text: str) -> str:
    """抖音编辑器在逐字输入时，话题转成芯片后紧邻的「#下一话题」易丢井号；在非空白字符后紧跟的 # 前插入空格。

    例：`#遥马农业#农资店` → `#遥马农业 #农资店`；`硬道理。#遥马农业#农资店` → `硬道理。 #遥马农业 #农资店`
    """
    if not text or "#" not in text:
        return text
    return re.sub(r"(?<=\S)#", " #", text)


async def _type_douyin_description_simulated(
    page: Page,
    edit_box,
    full_text: str,
    desc_delay: int,
    wait_ms: Callable[[int], int],
    metadata: Dict[str, Any],
    config: Dict[str, Any],
) -> None:
    """逐字 type + 多话题时段间停顿：不一次性写入，符合拟人发布节奏。"""
    if not full_text:
        return
    # 规范化后多个话题形如「… #甲 #乙」；按「空格+#」切分，每段仍逐字输入
    if " #" not in full_text or "#" not in full_text:
        await edit_box.type(full_text, delay=desc_delay)
        return
    parts: List[str] = [p for p in re.split(r"(?= #)", full_text) if p != ""]
    if len(parts) <= 1:
        await edit_box.type(full_text, delay=desc_delay)
        return
    pause_ms = wait_ms(550)
    for i, part in enumerate(parts):
        await edit_box.type(part, delay=desc_delay)
        if i < len(parts) - 1:
            try:
                from src.infrastructure.anti_risk.delays import random_delay

                await random_delay(page, pause_ms, metadata, config)
            except Exception:
                await page.wait_for_timeout(pause_ms)


def _desc_editor_selectors_for(metadata: Dict[str, Any]) -> list:
    """图文页优先匹配「添加作品描述」、editor-comp-publish、editor-kit-editor-container.old。"""
    base = list(Selectors.PUBLISH.get("DESC_EDITOR") or [])
    if (metadata.get("file_type") or "video").lower() != "image":
        return base
    keys = ("作品描述", "editor-comp-publish", "editor-kit-editor-container.old")
    pref = [s for s in base if any(k in s for k in keys)]
    rest = [s for s in base if s not in pref]
    return pref + rest


class MetadataFillStep(BasePublishStep):
    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        """填写元数据：标题 + 作品简介（含已确认的 #话题，与单发页解析规则一致）。"""
        await self._await_pause(metadata)
        title = metadata.get("title", "") or ""
        description = metadata.get("description", "") or ""
        tags = metadata.get("tags", []) or []
        tags = (
            tags
            if isinstance(tags, list)
            else [t.strip() for t in str(tags).split(",") if t.strip()]
        )

        _log_description_topic_preprocess(description, tags)

        logger.info(
            "开始填写元数据: 标题=%s..., 作品简介长度=%d",
            (title or "")[:20],
            len(description or ""),
        )

        # 发布速度倍率：界面「速度」设置，倍率越高输入与等待越慢
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        desc_delay = max(20, int(50 * speed_rate))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}

        # 抖音作品标题最多 30 个字，超出时截取前 30 个字
        _DOUYIN_TITLE_MAX = 30
        title_to_fill = title.strip()
        if len(title_to_fill) > _DOUYIN_TITLE_MAX:
            title_to_fill = title_to_fill[:_DOUYIN_TITLE_MAX]
            logger.warning("作品标题超过 %d 字已截断为: '%s'", _DOUYIN_TITLE_MAX, title_to_fill)
            USER_LOG.info(
                "[步骤4/9 作品描述] ⚠ 标题超过 %d 字（原长 %d 字），已自动截取前 %d 字填写",
                _DOUYIN_TITLE_MAX,
                len(title.strip()),
                _DOUYIN_TITLE_MAX,
            )

        # 1) 标题（拟人输入；有标题但找不到输入框则终止）
        if title_to_fill:
            title_filled = False
            for selector in _title_selectors_for(metadata):
                try:
                    title_input = page.locator(selector).first
                    if await title_input.count() > 0 and await title_input.is_visible():
                        try:
                            from src.infrastructure.anti_risk.human_like import human_type_text
                            await human_type_text(page, selector, title_to_fill, metadata, config)
                        except Exception:
                            await title_input.click()
                            await page.keyboard.press("Control+A")
                            await page.keyboard.press("Backspace")
                            await title_input.type(title_to_fill, delay=max(10, int(30 * speed_rate)))
                        logger.info(f"已填写标题: {selector}")
                        t_display = title_to_fill[:25] + "..." if len(title_to_fill) > 25 else title_to_fill or "（空）"
                        USER_LOG.info(f"[步骤4/9 作品描述] ▶ 标题已填写：{t_display}")
                        title_filled = True
                        break
                except Exception:
                    continue
            if not title_filled:
                USER_LOG.error("[步骤4/9 作品描述] ✗ 未找到标题输入框，终止发布")
                return PublishResult(success=False, error_message="未找到标题输入框", failed_step="步骤4/作品描述")

        # 作品简介输入框：只使用 DESC_EDITOR 中第一个选择器（按 file_type 排序后取首个）
        editor_selectors = _desc_editor_selectors_for(metadata)
        # 严格模式：只尝试第一个选择器，不遍历也不追加 placeholder 备选
        editor_selectors = editor_selectors[:1]

        for selector in editor_selectors:
            try:
                edit_box = page.locator(selector).first
                if await edit_box.count() > 0 and await edit_box.is_visible():
                    logger.info(f"找到编辑器: {selector}")
                    try:
                        from src.infrastructure.anti_risk.human_like import human_click
                        await human_click(page, edit_box, metadata, config)
                    except Exception:
                        await edit_box.click()
                    try:
                        from src.infrastructure.anti_risk.delays import random_delay
                        await random_delay(page, wait_ms(500), metadata, config)
                    except Exception:
                        await page.wait_for_timeout(wait_ms(500))

                    # 清空已有内容
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                    try:
                        from src.infrastructure.anti_risk.delays import random_delay
                        await random_delay(page, wait_ms(300), metadata, config)
                    except Exception:
                        await page.wait_for_timeout(wait_ms(300))

                    # 作品简介 = 全文（含已确认的 #话题），与单发页一致，不在此处再追加 tags
                    full_text = (description or title or "").strip()
                    raw_desc = full_text
                    full_text = _normalize_douyin_topic_spacing(full_text)
                    if full_text != raw_desc:
                        logger.info(
                            "作品简介已规范化话题间距（紧邻 # 前补空格），避免多话题逐键输入时部分井号丢失"
                        )

                    await _type_douyin_description_simulated(
                        page,
                        edit_box,
                        full_text,
                        desc_delay,
                        wait_ms,
                        metadata,
                        config,
                    )
                    if " #" in full_text and full_text.count("#") >= 2:
                        logger.info(
                            "作品简介按话题分段逐字输入，段间已插入拟人停顿（未使用一次性粘贴）"
                        )
                    try:
                        from src.infrastructure.anti_risk.delays import random_delay
                        await random_delay(page, wait_ms(400), metadata, config)
                    except Exception:
                        await page.wait_for_timeout(wait_ms(400))

                    # 仅当简介以 #关键词 结尾且无空格时，补按空格以在抖音端确认末尾话题
                    if full_text and re.search(r"#\S+$", full_text.rstrip()):
                        await page.keyboard.press("Space")
                        await page.wait_for_timeout(200)

                    # 严格后验：读回 innerText，为空则视为写入失败，返回发布失败
                    try:
                        actual_text = await page.evaluate(
                            "el => el.innerText",
                            await edit_box.element_handle()
                        )
                        if not (actual_text or "").strip():
                            logger.error("作品简介写入后验证失败：innerText 为空（sel=%s）", selector)
                            USER_LOG.error("[步骤4/9 作品描述] ✗ 作品简介写入验证失败（innerText 为空），终止发布")
                            return PublishResult(success=False, error_message="作品简介写入验证失败：innerText 为空", failed_step="步骤4/作品描述")
                    except Exception as ve:
                        logger.warning("innerText 验证异常（sel=%s）: %s", selector, ve)

                    logger.info("元数据填写完成（作品简介已含话题）")
                    desc_part = (description or title or "").strip()
                    desc_display = (desc_part[:35] + "...") if len(desc_part) > 35 else (desc_part or "（空）")
                    tag_count = len(tags) if isinstance(tags, list) and tags else 0
                    USER_LOG.info(f"[步骤4/9 作品描述] ✓ 作品简介已填写：{desc_display}，已确认话题数={tag_count}")
                    return None
            except Exception as e:
                logger.warning(f"使用选择器 {selector} 填写失败: {e}")
                continue

        USER_LOG.error("[步骤4/9 作品描述] ✗ 未找到作品描述编辑器，终止发布")
        return PublishResult(success=False, error_message="未找到作品描述编辑器", failed_step="步骤4/作品描述")
