# -*- coding: utf-8 -*-
"""
步骤2：进入发布页
文件路径: src/plugins/community/kuaishou/steps/step_02_entry.py

流程（视频）：
  1. 在创作者首页找到「发布视频」按钮并点击
  2. 等待页面跳转至发布页（URL 包含 article/publish/video）
  3. 检测未登录重定向
  4. 等待发布页特征元素可见，验证已进入发布页
  5. 若首页未找到按钮，回退为直接跳转 URL

流程（图文）：
  1. 在创作者首页点击「发布作品」展开下拉菜单
  2. 点击「发布图文」跳转到发布页
  3. 等待 URL 进入 /article/publish/video
  4. 切换「上传图文」Tab
  5. 等待图文发布页特征元素（拖拽上传区域）
  6. 处理「上次未发布图集」恢复弹窗（点放弃）
  7. 若首页入口失败，回退为直接跳转 URL + 切 Tab

字段依赖：
  metadata['file_type']: "video"（默认）或 "image"
"""
import logging
from typing import Dict, Any, Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from src.plugins.core.wait_helper import PluginWaitHelper
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from .wizard_utils import dismiss_kuaishou_publish_guides
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

PUBLISH_URL = "https://cp.kuaishou.com/article/publish/video"
# tabType=2 是快手图文发布页的 URL 参数，直接跳转无需切换 Tab
IMAGE_PUBLISH_URL = "https://cp.kuaishou.com/article/publish/video?tabType=2"


class EnterPublishEntryStep(BasePublishStep):
    """在快手创作者首页点击发布入口，进入视频或图文发布页。"""

    def __init__(self, upload_url: Optional[str] = None):
        self.upload_url = upload_url or PUBLISH_URL

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        file_type = (metadata.get("file_type") or "video").lower()
        is_image = file_type == "image"

        target_url = IMAGE_PUBLISH_URL if is_image else self.upload_url
        logger.info(f"===== 进入发布页: {target_url}（类型={file_type}）=====")
        step_label = self._step_prefix(metadata, "点击发布按钮").strip("[]")
        USER_LOG.info(f"[{step_label}] ▶ 跳转 {target_url}（{file_type}）")

        if is_image:
            return await self._enter_image_publish(page, metadata, step_label)
        else:
            return await self._enter_video_publish(page, metadata, step_label)

    # ------------------------------------------------------------------
    # 视频发布入口（原有逻辑）
    # ------------------------------------------------------------------

    async def _enter_video_publish(
        self, page: Page, metadata: Dict[str, Any], step_label: str
    ) -> StepOutcome:
        clicked = await self._click_publish_btn(page)

        if clicked:
            try:
                await page.wait_for_url(
                    f"**{self.upload_url}**",
                    timeout=12000,
                    wait_until="domcontentloaded",
                )
                logger.debug("步骤2: URL 已跳转至发布页")
            except PlaywrightTimeoutError:
                if self.upload_url not in page.url:
                    logger.debug("步骤2: 按钮点击后 URL 未变化，回退直接导航")
                    clicked = False

        if not clicked:
            logger.info("步骤2: 未点击到发布按钮，直接跳转 URL")
            try:
                await page.goto(self.upload_url, timeout=30000, wait_until="domcontentloaded")
            except Exception as e:
                return PublishResult(success=False, error_message=f"进入发布页失败: {e}")

        return await self._verify_publish_page(page, metadata, step_label, is_image=False)

    # ------------------------------------------------------------------
    # 图文发布入口（新增）
    # ------------------------------------------------------------------

    async def _enter_image_publish(
        self, page: Page, metadata: Dict[str, Any], step_label: str
    ) -> StepOutcome:
        """
        进入图文发布页。
        策略（优先级由高到低）：
          1. 已在图文发布页（URL 含 tabType=2）→ 直接使用
          2. 直接跳转 IMAGE_PUBLISH_URL（?tabType=2）→ 最稳定，无需切 Tab
          3. 首页点「发布作品」→「发布图文」下拉 → 跳转后若 URL 没有 tabType=2 则补充跳转
        """
        current_url = page.url

        # 已在图文发布页
        if "tabType=2" in current_url:
            logger.debug("步骤2(图文): 已在图文发布页（tabType=2），无需跳转")
        else:
            # 主路：直接导航到带 tabType=2 的 URL（最稳定，绕过 Tab 切换）
            # 同时尝试首页下拉入口，失败则回退到直接跳转
            clicked = await self._click_image_publish_btn(page)

            if clicked:
                try:
                    # 等待跳转，接受含或不含 tabType=2 的 URL
                    await page.wait_for_url(
                        "**/article/publish/video**",
                        timeout=12000,
                        wait_until="domcontentloaded",
                    )
                    logger.debug("步骤2(图文): URL 已跳转至发布页")
                except PlaywrightTimeoutError:
                    if "article/publish/video" not in page.url:
                        clicked = False

            # 无论是否点击成功，都确保最终 URL 含 tabType=2
            if "tabType=2" not in page.url:
                logger.info("步骤2(图文): 直接跳转 %s", IMAGE_PUBLISH_URL)
                try:
                    await page.goto(IMAGE_PUBLISH_URL, timeout=30000, wait_until="domcontentloaded")
                except Exception as e:
                    return PublishResult(success=False, error_message=f"进入图文发布页失败: {e}")

        # 登录重定向检测
        err = self._check_redirect(page)
        if err:
            return err

        # 处理「上次未发布图集」恢复弹窗
        await self._dismiss_draft_recovery(page)

        return await self._verify_publish_page(page, metadata, step_label, is_image=True)

    async def _click_image_publish_btn(self, page: Page) -> bool:
        """
        点击顶部「发布作品」→ 等待下拉展开 → 点击「发布图文」。
        已在发布页则直接返回 True；不在快手域则返回 False。
        """
        current_url = page.url

        if "article/publish/video" in current_url:
            logger.debug("步骤2(图文): 已在发布页，无需点击按钮")
            return True

        if "cp.kuaishou.com" not in current_url:
            logger.debug("步骤2(图文): 当前不在快手域，跳过按钮点击")
            return False

        # 1. 点「发布作品」展开下拉
        work_btn_sels = Selectors.HOME.get("PUBLISH_WORK_BTN", [])
        clicked_work = False
        for sel in work_btn_sels:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.scroll_into_view_if_needed()
                    await btn.click()
                    clicked_work = True
                    logger.debug("步骤2(图文): 已点击「发布作品」，sel=%s", sel)
                    break
            except Exception as e:
                logger.debug("步骤2(图文): 「发布作品」选择器 %s 失败: %s", sel, e)

        if not clicked_work:
            logger.debug("步骤2(图文): 未找到「发布作品」按钮")
            return False

        # 2. 等待「发布图文」选项出现（下拉延迟展开）
        image_btn_sels = Selectors.HOME.get("PUBLISH_IMAGE_BTN", [])
        for sel in image_btn_sels:
            try:
                item = page.locator(sel).first
                await item.wait_for(state="visible", timeout=4000)
                await item.click()
                logger.debug("步骤2(图文): 已点击「发布图文」，sel=%s", sel)
                return True
            except Exception as e:
                logger.debug("步骤2(图文): 「发布图文」选择器 %s 失败: %s", sel, e)

        logger.debug("步骤2(图文): 未找到「发布图文」下拉项")
        return False

    async def _dismiss_draft_recovery(self, page: Page) -> None:
        """处理「还有上次未发布的图集，是否继续编辑？」弹窗，点「放弃」从空白开始。"""
        dialog_sels = Selectors.HOME.get("IMAGE_DRAFT_RECOVERY_DIALOG", [])
        discard_sels = Selectors.HOME.get("IMAGE_DRAFT_DISCARD_BTN", [])
        for sel in dialog_sels:
            try:
                if await page.locator(sel).first.is_visible():
                    logger.info("步骤2(图文): 检测到上次未发布图集弹窗，点击「放弃」")
                    for btn_sel in discard_sels:
                        try:
                            btn = page.locator(btn_sel).first
                            if await btn.count() > 0 and await btn.is_visible():
                                await btn.click()
                                await page.wait_for_timeout(500)
                                return
                        except Exception:
                            pass
            except Exception:
                pass

    async def _switch_to_image_tab(self, page: Page) -> None:
        """切换到「上传图文」Tab（若已在该 Tab 则跳过）。"""
        tab_sels = Selectors.HOME.get("IMAGE_PUBLISH_TAB", [])
        for sel in tab_sels:
            try:
                tab = page.locator(sel).first
                if await tab.count() > 0:
                    await tab.wait_for(state="visible", timeout=6000)
                    await tab.click()
                    logger.info("步骤2(图文): 已切换到「上传图文」Tab，sel=%s", sel)
                    await PluginWaitHelper.wait_for_any_visible(
                        page,
                        Selectors.HOME.get("IMAGE_PUBLISH_PAGE_MARKERS", []),
                        timeout_ms=3000,
                        poll_interval_ms=250,
                    )
                    return
            except Exception as e:
                logger.debug("步骤2(图文): Tab 切换选择器 %s 失败: %s", sel, e)
        logger.warning("步骤2(图文): 未找到「上传图文」Tab，继续尝试后续步骤")

    # ------------------------------------------------------------------
    # 通用：登录重定向检测 & 发布页验证
    # ------------------------------------------------------------------

    def _check_redirect(self, page: Page) -> Optional[PublishResult]:
        current_url = page.url
        redirect_keywords = Selectors.REDIRECT.get("LOGIN_URLS", ["login", "signin", "passport"])
        if any(kw in current_url.lower() for kw in redirect_keywords):
            logger.warning(f"被重定向到登录页: {current_url}")
            return PublishResult(success=False, error_message="Cookie 已过期，被重定向到登录页")
        return None

    async def _verify_publish_page(
        self, page: Page, metadata: Dict[str, Any], step_label: str, is_image: bool
    ) -> StepOutcome:
        """等待发布页特征元素可见，确认已成功进入发布页。"""
        err = self._check_redirect(page)
        if err:
            return err

        if is_image:
            markers = Selectors.HOME.get("IMAGE_PUBLISH_PAGE_MARKERS", [])
            markers_key = "IMAGE_PUBLISH_PAGE_MARKERS"
        else:
            markers = Selectors.HOME.get("VIDEO_PUBLISH_PAGE_MARKERS", [])
            markers_key = "VIDEO_PUBLISH_PAGE_MARKERS"

        primary_marker = markers[0] if markers else None
        if not primary_marker:
            return PublishResult(
                success=False,
                error_message=f"发布页特征元素选择器未配置（{markers_key} 为空），请检查 selectors.py",
            )

        matched_marker = await PluginWaitHelper.wait_for_any_visible(
            page,
            markers,
            timeout_ms=12000,
            poll_interval_ms=300,
            pause_callback=lambda: self._await_pause(metadata),
        )
        ok = bool(matched_marker)
        try:
            loc = page.locator(primary_marker).first
            await loc.wait_for(state="visible", timeout=1 if ok else 12000)
            ok = True
            logger.info("已检测到发布页特征元素（is_visible）: %s", primary_marker)
        except Exception:
            pass

        if not ok:
            # 尝试备用 markers
            for sel in markers[1:]:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        ok = True
                        logger.info("发布页备用特征元素命中: %s", sel)
                        break
                except Exception:
                    pass

        if not ok:
            current_url = page.url
            return PublishResult(
                success=False,
                error_message=f"未能确认进入{'图文' if is_image else '视频'}发布页：特征元素未出现（sel={primary_marker}，url={current_url}）",
            )

        await dismiss_kuaishou_publish_guides(page, metadata)

        USER_LOG.info(f"[{step_label}] ✓ 已进入{'图文' if is_image else '视频'}发布页")
        return None

    # ------------------------------------------------------------------

    async def _click_publish_btn(self, page: Page) -> bool:
        """
        视频发布：在当前页面查找「发布视频」入口按钮并点击。
        已在发布页则直接返回 True；不在快手域则返回 False。
        """
        current_url = page.url

        if "article/publish/video" in current_url:
            logger.debug("步骤2: 已在发布页，无需点击按钮")
            return True

        if "cp.kuaishou.com" not in current_url:
            logger.debug("步骤2: 当前不在快手域，跳过按钮点击")
            return False

        btn_selectors = Selectors.HOME.get("PUBLISH_VIDEO_BTN", [])
        for sel in btn_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.scroll_into_view_if_needed()
                    await btn.click()
                    logger.debug("步骤2: 已点击「发布视频」按钮，选择器=%s", sel)
                    return True
            except Exception as e:
                logger.debug("步骤2: 发布按钮选择器 %s 失败: %s", sel, e)

        logger.debug("步骤2: 未在首页找到「发布视频」按钮")
        return False
