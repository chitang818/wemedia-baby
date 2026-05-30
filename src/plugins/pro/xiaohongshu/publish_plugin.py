# -*- coding: utf-8 -*-
"""
小红书发布插件（步骤链版本）
文件路径：src/plugins/pro/xiaohongshu/publish_plugin.py

采用与抖音/视频号插件一致的「步骤链 + StepRunner」架构：
    步骤1: 导航首页
    步骤2: 进入发布页
    步骤3: 上传素材（视频/图文）
    步骤4: 封面设置
    步骤5: 填写描述（标题、正文、话题）
    步骤6A: 原创申明（占位）
    步骤6B: 作品申明（占位）
    步骤6C: 添加地点（占位）
    步骤7: 发布设置（视频：可见性+定时；图文：合拍+正文复制+可见性+定时）
    步骤8: 点击发布
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from playwright.async_api import Page

from src.infrastructure.common.bundled_config import load_platform_bundle
from src.plugins.core.interfaces.publish_plugin import (
    PublishPluginInterface,
    PublishResult,
    FormField,
)

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

_DEFAULT_LIMITS = {
    "title_max_length": 20,
    "description_max_length": 1000,
    "max_topics": 10,
}


def _platform_config() -> Dict[str, Any]:
    """从内置 config/platforms/xiaohongshu.json 读取平台配置。"""
    return load_platform_bundle("xiaohongshu")


def _load_limits() -> Dict[str, int]:
    """优先从 config/platforms/xiaohongshu.json 读取 limits，否则从插件 config.json，否则使用默认值。"""
    try:
        data = _platform_config()
        if isinstance(data.get("limits"), dict):
            return {**_DEFAULT_LIMITS, **data["limits"]}
    except Exception:
        pass
    try:
        plugin_config = Path(__file__).resolve().parent / "config.json"
        if plugin_config.exists():
            data = json.loads(plugin_config.read_text(encoding="utf-8"))
            if isinstance(data.get("limits"), dict):
                return {**_DEFAULT_LIMITS, **data["limits"]}
    except Exception:
        pass
    return _DEFAULT_LIMITS.copy()


class XiaohongshuPublishPlugin(PublishPluginInterface):
    """小红书发布插件 — 步骤链模式（8步）"""

    UPLOAD_URL = "https://creator.xiaohongshu.com/publish/publish"
    LOGIN_URL_KEYWORDS = ["login"]
    LOGIN_TEXT_INDICATORS = ["扫码登录", "短信登录", "密码登录"]

    @property
    def platform_id(self) -> str:
        return "xiaohongshu"

    def get_form_schema(self, content_type: str = "video") -> List[FormField]:
        """返回发布表单定义。"""
        limits = _load_limits()
        title_max = limits.get("title_max_length", 20)
        desc_max = limits.get("description_max_length", 1000)
        schema = [
            FormField(
                name="title",
                label="标题",
                field_type="text",
                placeholder="输入笔记标题（最多20字）",
                max_length=title_max,
            ),
            FormField(
                name="description",
                label="正文",
                field_type="textarea",
                placeholder="输入笔记正文...",
                max_length=desc_max,
            ),
            FormField(
                name="tags",
                label="话题",
                field_type="text",
                required=False,
                placeholder="话题标签，用逗号隔开",
            ),
        ]
        return schema

    async def publish(
        self,
        context: Page,
        file_path: str,
        metadata: Dict[str, Any],
    ) -> PublishResult:
        """执行小红书自动发布流程（8步步骤链）

        Args:
            context: Playwright Page 对象（已注入账号凭证）
            file_path: 本地文件路径（视频或图片）
            metadata: 元数据字典，包含 title, description, tags 等

        Returns:
            PublishResult 发布结果
        """
        page = context
        try:
            logger.info("===== 小红书发布插件启动 =====")
            logger.info(f"目标文件: {file_path}")
            USER_LOG.info("发布流程 - 开始")

            from .steps.step_01_home import NavigateHomeStep
            from .steps.step_02_entry import EnterPublishEntryStep
            from .steps.step_03_upload import UploadMediaStep
            from .steps.step_04_cover import CoverSettingStep
            from .steps.step_05_description import MetadataFillStep
            from .steps.step_06A_original_declaration import OriginalDeclarationStep
            from .steps.step_06B_work_declaration import WorkDeclarationStep
            from .steps.step_06C_location import LocationStep
            from .steps.step_07_settings import PublishSettingsStep
            from .steps.step_08_submit import SubmitStep
            from .steps.step_09_post_publish import PostPublishBrowseStep
            from .steps.step_runner import StepRunner, RunnerConfig

            steps = [
                NavigateHomeStep(),
                EnterPublishEntryStep(),
                UploadMediaStep(),
                CoverSettingStep(),
                MetadataFillStep(),
                OriginalDeclarationStep(),
                WorkDeclarationStep(),
                LocationStep(),
                PublishSettingsStep(),
                SubmitStep(),
                PostPublishBrowseStep(),
            ]

            platform_data = _platform_config()
            anti_risk_config = (
                platform_data.get("anti_risk")
                if isinstance(platform_data.get("anti_risk"), dict)
                else {}
            )
            from .selectors import Selectors

            # pierce（>>）对 closed Shadow 无效，仅作参考；以诊断包 xhs_publish_probe.json 为准
            probes: Dict[str, Any] = {
                "xhs_publish_host": (
                    ".publish-page-content xhs-publish-btn[is-publish='true'], "
                    "xhs-publish-btn[is-publish='true']"
                ),
                "schedule_wrapper": ", ".join(
                    Selectors.SETTINGS.get("SCHEDULE_WRAPPER", []) or [],
                ),
                "schedule_picker": ", ".join(
                    Selectors.SETTINGS.get("SCHEDULE_DATE_PICKER", []) or [],
                ),
            }
            try:
                from src.infrastructure.common.config.app_config_merge import get_app_config_for_read

                app_cfg = get_app_config_for_read()
            except Exception:
                app_cfg = {}
            auto_click_submit = bool(
                metadata.get(
                    "xhs_auto_click_submit",
                    app_cfg.get("xiaohongshu_auto_click_submit_high_risk", False),
                )
            )
            metadata_for_runner = {
                **metadata,
                "anti_risk_config": anti_risk_config,
                "selector_probes": probes,
                "browser_fingerprint_strategy": "strict_real_browser",
                "xhs_strict_real_browser": True,
                "xhs_auto_click_submit": auto_click_submit,
                "xhs_manual_submit_timeout_seconds": metadata.get(
                    "xhs_manual_submit_timeout_seconds",
                    app_cfg.get("xiaohongshu_manual_submit_timeout_seconds", 600),
                ),
            }

            runner = StepRunner(
                page=page,
                file_path=file_path,
                metadata=metadata_for_runner,
                config=RunnerConfig(
                    max_step_retries=3,
                    step_retry_delay_seconds=1.5,
                    max_submit_retries=2,
                ),
                action_handlers={},
            )

            result = await runner.run(steps)
            if result.success:
                USER_LOG.info("发布流程 - 完成")
            else:
                USER_LOG.warning(f"发布流程 - 失败: {(result.error_message or '')[:50]}")
            return result

        except Exception as e:
            logger.error(f"小红书发布插件异常: {e}", exc_info=True)
            USER_LOG.warning("发布流程 - 失败: 插件异常")
            return PublishResult(success=False, error_message=f"插件执行异常: {str(e)}")
