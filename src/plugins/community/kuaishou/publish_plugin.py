"""
快手发布插件
文件路径：src/plugins/community/kuaishou/publish_plugin.py
功能：基于步骤链 + StepRunner 完成快手创作者平台视频发布
"""
from pathlib import Path
from typing import List, Dict, Any
import logging
import json

from src.infrastructure.browser.automation_api import Page

from src.infrastructure.common.bundled_config import load_platform_bundle
from src.plugins.core.interfaces.publish_plugin import PublishPluginInterface, PublishResult, FormField
from .selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

_DEFAULT_LIMITS = {"title_max_length": 50, "description_max_length": 1000, "max_topics": 4}


def _platform_config() -> Dict[str, Any]:
    """从内置 config/platforms/kuaishou.json 读取平台配置（含 limits、anti_risk）。"""
    return load_platform_bundle("kuaishou")


def _load_limits() -> Dict[str, int]:
    """优先从 config/platforms/kuaishou.json 的 limits 读取，否则从插件 config.json，否则默认值。"""
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


class KuaishouPublishPlugin(PublishPluginInterface):
    """快手发布插件 - 视频与图文统一为 11 个进度阶段；图文在第 6 阶段内依次执行 6a(音乐)+6b(作者服务)。"""

    @property
    def platform_id(self) -> str:
        return "kuaishou"

    def get_form_schema(self, content_type: str = "video") -> List[FormField]:
        """返回发布表单定义；max_length 等从配置 limits 读取。"""
        limits = _load_limits()
        title_max = limits.get("title_max_length")
        desc_max = limits.get("description_max_length")
        return [
            FormField(name="title", label="标题", field_type="text", placeholder="输入视频标题", max_length=title_max),
            FormField(name="description", label="描述", field_type="textarea", placeholder="输入作品描述...", max_length=desc_max),
            FormField(name="tags", label="话题", field_type="text", required=False, placeholder="话题, 用逗号隔开"),
        ]

    async def publish(
        self,
        context: Page,
        file_path: str,
        metadata: Dict[str, Any],
    ) -> PublishResult:
        """执行快手自动发布流程（步骤链 + StepRunner）。

        步骤链差异（进度均为 [步骤X/11]）：
          视频：步骤1~5 → 6 仅作者服务(6b) → 7~11
          图文：步骤1~5 → 6 先音乐(6a) 再作者服务(6b)，同属第 6 阶段 → 7~11
        """
        page = context
        try:
            logger.info("===== 快手发布插件启动 =====")
            logger.info(f"目标文件: {file_path}")
            USER_LOG.info("发布流程 - 开始")

            from .steps.step_01_home import NavigateHomeStep
            from .steps.step_02_entry import EnterPublishEntryStep
            from .steps.step_03_upload import UploadMediaStep
            from .steps.step_04_description import MetadataFillStep
            from .steps.step_05_cover import CoverSettingStep
            from .steps.step_06a_music import MusicSettingStep
            from .steps.step_06b_author_service import AuthorServiceStep
            from .steps.step_07_manage_hotspot import ManageHotspotStep
            from .steps.step_08_author_statement import AuthorStatementStep
            from .steps.step_09_location import LocationStep
            from .steps.step_10_settings import PublishSettingsStep
            from .steps.step_11_submit import SubmitStep
            from .steps.step_runner import StepRunner, RunnerConfig

            is_image = metadata.get("publish_type") == "image"

            # 公共前段：步骤 1~5
            common_pre = [
                NavigateHomeStep(),
                EnterPublishEntryStep(),
                UploadMediaStep(),
                MetadataFillStep(),
                CoverSettingStep(),
            ]
            # 步骤 6：图文多一个音乐步骤
            step6 = [MusicSettingStep(), AuthorServiceStep()] if is_image else [AuthorServiceStep()]
            # 公共后段：步骤 7~11
            common_post = [
                ManageHotspotStep(),
                AuthorStatementStep(),
                LocationStep(),
                PublishSettingsStep(),
                SubmitStep(),
            ]
            steps = common_pre + step6 + common_post

            n_exec = len(steps)
            logger.info(
                "发布类型=%s，进度共 11 阶段（实际执行 %d 个子步骤；图文时第 6 阶段含 6a+6b）",
                "图文" if is_image else "视频",
                n_exec,
            )

            platform_data = _platform_config()
            anti_risk_config = (
                platform_data.get("publish_pacing")
                if isinstance(platform_data.get("publish_pacing"), dict)
                else platform_data.get("anti_risk")
                if isinstance(platform_data.get("anti_risk"), dict)
                else {}
            )
            probes = {
                "file_input": ", ".join(Selectors.PUBLISH.get("FILE_INPUT", [])),
                "upload_success": ", ".join(Selectors.PUBLISH.get("UPLOAD_SUCCESS_MARKER", [])),
                "desc_editor": ", ".join(Selectors.PUBLISH.get("DESC_EDITOR", [])),
                "submit_btn": ", ".join(Selectors.PUBLISH.get("SUBMIT_BTN", [])),
                "title_input": ", ".join(Selectors.PUBLISH.get("TITLE_INPUT", [])),
            }
            metadata_for_runner = {**metadata, "selector_probes": probes, "anti_risk_config": anti_risk_config}

            action_handlers = {
                "need_supplement": lambda: [SubmitStep()],
            }

            runner = StepRunner(
                page=page,
                file_path=file_path,
                metadata=metadata_for_runner,
                config=RunnerConfig(),
                action_handlers=action_handlers,
            )
            result = await runner.run(steps)
            if result.success:
                USER_LOG.info("发布流程 - 完成")
            else:
                USER_LOG.warning(f"发布流程 - 失败: {(result.error_message or '')[:50]}")
            return result
        except Exception as e:
            logger.error(f"快手发布插件异常: {e}", exc_info=True)
            USER_LOG.warning("发布流程 - 失败: 插件异常")
            return PublishResult(success=False, error_message=f"插件执行异常: {str(e)}")
