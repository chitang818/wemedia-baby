# -*- coding: utf-8 -*-
"""
头条号发布插件（步骤链版本）
文件路径：src/plugins/pro/toutiao/publish_plugin.py

采用与抖音/视频号/小红书插件一致的「步骤链 + StepRunner」架构：
    步骤1: 导航首页
    步骤2: 进入发布页
    步骤3: 上传视频
    步骤4: 填写描述（标题、简介、标签）
    步骤5: 封面设置
    步骤6: 发布设置（定时、原创声明）
    步骤7: 点击发布
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from src.infrastructure.browser.automation_api import Page

from src.infrastructure.common.bundled_config import load_platform_bundle
from src.plugins.core.interfaces.publish_plugin import (
    PublishPluginInterface,
    PublishResult,
    FormField,
)

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

_DEFAULT_LIMITS = {
    "title_max_length": 30,
    "description_max_length": 2000,
    "max_tags": 5,
}


def _platform_config() -> Dict[str, Any]:
    """从内置 config/platforms/toutiao.json 读取平台配置。"""
    return load_platform_bundle("toutiao")


def _load_limits() -> Dict[str, int]:
    """优先从 config/platforms/toutiao.json 读取 limits，否则从插件 config.json，否则使用默认值。"""
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


class ToutiaoPublishPlugin(PublishPluginInterface):
    """头条号发布插件 — 步骤链模式（7步）"""

    UPLOAD_URL = "https://mp.toutiao.com/profile_v4/xigua/upload"
    LOGIN_URL_KEYWORDS = ["login", "auth"]
    LOGIN_TEXT_INDICATORS = ["扫码登录", "短信登录", "密码登录"]

    @property
    def platform_id(self) -> str:
        return "toutiao"

    def get_form_schema(self, content_type: str = "video") -> List[FormField]:
        """返回发布表单定义。"""
        limits = _load_limits()
        title_max = limits.get("title_max_length", 30)
        desc_max = limits.get("description_max_length", 2000)
        schema = [
            FormField(
                name="title",
                label="标题",
                field_type="text",
                placeholder="输入视频标题",
                max_length=title_max,
            ),
            FormField(
                name="description",
                label="简介",
                field_type="textarea",
                required=False,
                placeholder="输入视频简介...",
                max_length=desc_max,
            ),
            FormField(
                name="tags",
                label="标签",
                field_type="text",
                required=False,
                placeholder="标签，用逗号隔开",
            ),
        ]
        return schema

    async def publish(
        self,
        context: Page,
        file_path: str,
        metadata: Dict[str, Any],
    ) -> PublishResult:
        """执行头条号自动发布流程（7步步骤链）"""
        page = context
        try:
            logger.info("===== 头条号发布插件启动 =====")
            logger.info(f"目标文件: {file_path}")
            USER_LOG.info("发布流程 - 开始")

            from .steps.step_01_home import NavigateHomeStep
            from .steps.step_02_entry import EnterPublishEntryStep
            from .steps.step_03_upload import UploadMediaStep
            from .steps.step_04_description import MetadataFillStep
            from .steps.step_05_cover import CoverSettingStep
            from .steps.step_06_settings import PublishSettingsStep
            from .steps.step_07_submit import SubmitStep
            from .steps.step_runner import StepRunner, RunnerConfig

            steps = [
                NavigateHomeStep(),
                EnterPublishEntryStep(),
                UploadMediaStep(),
                MetadataFillStep(),
                CoverSettingStep(),
                PublishSettingsStep(),
                SubmitStep(),
            ]

            platform_data = _platform_config()
            anti_risk_config = (
                platform_data.get("publish_pacing")
                if isinstance(platform_data.get("publish_pacing"), dict)
                else platform_data.get("anti_risk")
                if isinstance(platform_data.get("anti_risk"), dict)
                else {}
            )
            metadata_for_runner = {**metadata, "anti_risk_config": anti_risk_config}

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
            logger.error(f"头条号发布插件异常: {e}", exc_info=True)
            USER_LOG.warning("发布流程 - 失败: 插件异常")
            return PublishResult(success=False, error_message=f"插件执行异常: {str(e)}")
