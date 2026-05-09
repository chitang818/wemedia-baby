# -*- coding: utf-8 -*-
"""
步骤4：作品描述（简介、话题）
文件路径: src/plugins/community/kuaishou/steps/step_04_description.py

流程：
  1. 填写简介与话题（快手发布页无独立标题框，仅使用 description 字段）
"""
import logging
import re
from typing import Any, Dict, List, Set

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from .wizard_utils import dismiss_kuaishou_publish_guides

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class MetadataFillStep(BasePublishStep):
    """填写作品描述与话题（快手发布页无独立标题框）。"""

    # 快手作品简介中话题上限（超出则仅保留按顺序出现的前若干个）
    KS_MAX_TOPICS = 4

    @staticmethod
    def _normalize_tag(tag: str) -> str:
        tag = (tag or "").strip()
        if not tag:
            return ""
        # 统一去掉用户可能输入的前导 '#'
        return tag.lstrip("#").strip()

    @classmethod
    def _ordered_topics_from_description(cls, text: str) -> List[str]:
        """按文案从左到右顺序提取 #话题（去重，保留首次出现顺序）。"""
        ordered: List[str] = []
        seen: Set[str] = set()
        for m in re.finditer(r"#\s*([^\s#]+)", text or ""):
            nt = cls._normalize_tag(m.group(1))
            if nt and nt not in seen:
                seen.add(nt)
                ordered.append(nt)
        return ordered

    def _build_description_with_topic_limit(
        self, description: str, tags: List[Any]
    ) -> tuple[str, List[str], int]:
        """
        合并简介内 #话题 与任务 tags，去重后仅保留前 KS_MAX_TOPICS 个。
        返回 (正文纯文本, 实际保留的话题列表, 截断前话题总数)。

        注意：快手富文本编辑器需要在 #话题名 后按空格才能识别为话题链接，
        因此正文和话题分开返回，由调用方分别输入。
        """
        from_desc = self._ordered_topics_from_description(description)
        seen = set(from_desc)
        merged = list(from_desc)
        for t in tags:
            nt = self._normalize_tag(str(t))
            if nt and nt not in seen:
                seen.add(nt)
                merged.append(nt)
        total_before_limit = len(merged)
        kept = merged[: self.KS_MAX_TOPICS]
        # 从描述中剥除所有 #话题 标记，得到纯文本正文
        body = re.sub(r"#\s*[^\s#]+", " ", description or "")
        body = re.sub(r"\s+", " ", body).strip()
        return body, kept, total_before_limit

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        _p = self._step_prefix(metadata, "添加作品描述")
        description = (metadata.get("description") or "").strip()
        tags = metadata.get("tags") or []
        if not isinstance(tags, list):
            tags = [t.strip() for t in str(tags).split(",") if t.strip()]

        logger.info(f"开始填写元数据: 描述长度={len(description)}, 任务话题数={len(tags)}")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        config = metadata.get("anti_risk_config") or {}

        # 新手引导 / 作品信息向导（含 react-joyride、Ant 弹窗等）
        await dismiss_kuaishou_publish_guides(page, metadata)

        # 作品描述 + 话题（快手最多 4 个话题，超出只保留前 4 个）
        # 注意：正文和话题分开返回，话题需逐个输入并按空格确认
        body_text, topics_kept, topic_total = self._build_description_with_topic_limit(description, tags)
        if topic_total > self.KS_MAX_TOPICS:
            logger.info(
                f"话题数 {topic_total} 超过快手上限 {self.KS_MAX_TOPICS}，已截断为前 {self.KS_MAX_TOPICS} 个"
            )
        if body_text or topics_kept:
            # 严格模式：只使用 #work-description-edit（DOM 分析报告稳定标识）
            primary_sel = "#work-description-edit"
            desc_box = page.locator(primary_sel).first
            try:
                await desc_box.wait_for(state="visible", timeout=5000)
            except Exception:
                USER_LOG.error("%s ✗ 未找到描述编辑器（sel=%s），终止发布", _p, primary_sel)
                return PublishResult(success=False, error_message=f"未找到描述编辑器（sel={primary_sel}）", failed_step="步骤4/作品描述")

            # 点击激活输入框（跳过 operation_delay，避免额外等待）
            try:
                from src.infrastructure.anti_risk.human_like import human_click
                await human_click(page, desc_box, metadata, config, use_operation_delay=False)
            except Exception:
                await desc_box.click()
            # 清空现有内容
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Delete")
            await page.wait_for_timeout(200)

            # ── 阶段1：输入正文（不含话题）────────────────────────────────
            if body_text:
                typed_ok = False
                try:
                    from src.infrastructure.anti_risk.human_like import human_type_text
                    await human_type_text(
                        page, primary_sel, body_text, metadata, config,
                        use_operation_delay=False,  # 跳过 operation_delay，节省 0.5-3s
                    )
                    typed_ok = True
                except Exception as te:
                    logger.debug(f"human_type_text 失败，降级为 type(): {te}")
                if not typed_ok:
                    await desc_box.type(body_text, delay=max(20, int(50 * speed_rate)))

            # ── 阶段2：逐个输入话题并按空格确认 ──────────────────────────
            # 核心原因：快手编辑器（React/Haploid）依靠键盘事件（keydown/input）识别话题；
            # execCommand/fill() 绕过了键盘事件链，导致识别失败。
            # 话题部分必须始终用 keyboard.type() 逐字触发，与手动输入等效。
            if topics_kept:
                # 确保焦点在编辑器末尾（click 可能把光标放中间，用 Control+End 更准）
                await desc_box.click()
                await page.keyboard.press("Control+End")
                await page.wait_for_timeout(150)

            for i, tag in enumerate(topics_kept):
                # 前置空格分隔（正文不为空或非第一个话题时需要）
                if body_text or i > 0:
                    await page.keyboard.type(" ")
                    await page.wait_for_timeout(80)
                # 逐字输入 #话题名（keyboard.type 逐字触发 keydown/input，与手动输入等效）
                await page.keyboard.type(f"#{tag}", delay=max(30, int(50 * speed_rate)))
                await page.wait_for_timeout(200)
                # 按空格触发快手编辑器的话题识别（与手动输入 #话题名<空格> 完全相同）
                await page.keyboard.press("Space")
                await page.wait_for_timeout(350)

            # 严格后验：读回 innerText，为空则视为写入失败，返回发布失败
            try:
                actual = await page.evaluate(
                    "el => el.innerText",
                    await desc_box.element_handle()
                )
                if not (actual or "").strip():
                    logger.error("作品描述写入后验证失败：innerText 为空（sel=%s）", primary_sel)
                    USER_LOG.error("%s ✗ 作品描述写入验证失败（innerText 为空），终止发布", _p)
                    return PublishResult(success=False, error_message="作品描述写入验证失败：innerText 为空", failed_step="步骤4/作品描述")
            except Exception as ve:
                logger.warning("innerText 验证异常（sel=%s）: %s", primary_sel, ve)

            logger.info(f"已填写作品描述与话题，选择器={primary_sel}")
            USER_LOG.info(
                f"{_p} ✓ 作品简介已填写，话题数={len(topics_kept)}"
                + (f"（已按平台上限保留前 {self.KS_MAX_TOPICS} 个）" if topic_total > self.KS_MAX_TOPICS else "")
            )

        USER_LOG.info(f"{_p} ✓ 完成")
        return None
