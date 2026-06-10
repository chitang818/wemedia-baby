"""
抖音发布插件
文件路径：src/plugins/community/douyin/publish_plugin.py
功能：基于 Playwright 自动化完成抖音创作者平台的内容发布
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
import json
import asyncio
from src.infrastructure.browser.automation_api import Page

from src.infrastructure.common.bundled_config import load_platform_bundle
from src.plugins.core.interfaces.publish_plugin import PublishPluginInterface, PublishResult, FormField
from .selectors import Selectors

logger = logging.getLogger(__name__)
# 用户可见的简洁日志（发布日志界面仅展示此 logger）
USER_LOG = logging.getLogger("publish.user_log")

# 默认限制（当配置文件无 limits 时使用）
_DEFAULT_LIMITS = {"title_max_length": 55, "description_max_length": 500, "max_topics": 10}


def _platform_config() -> Dict[str, Any]:
    """从内置 config/platforms/douyin.json 读取平台配置（含 limits、anti_risk）。"""
    return load_platform_bundle("douyin")


def _load_limits() -> Dict[str, int]:
    """优先从 config/platforms/douyin.json 读取 limits，否则从插件 config.json，否则使用默认值。"""
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


class DouyinPublishPlugin(PublishPluginInterface):
    """抖音发布插件 - 负责在抖音创作者平台执行自动化视频发布"""

    # ========== 抖音创作者平台关键常量 ==========
    UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
    # 用于检测未登录状态的 URL 关键词列表
    LOGIN_URL_KEYWORDS = ["login", "passport", "sso"]
    # 用于检测页面中出现登录组件的文字列表
    LOGIN_TEXT_INDICATORS = ["密码登录", "短信登录", "扫码登录", "验证码登录"]

    @property
    def platform_id(self) -> str:
        return "douyin"

    def get_form_schema(self, content_type: str = "video") -> List[FormField]:
        """返回发布表单定义；max_length 等从配置 limits 读取。"""
        limits = _load_limits()
        title_max = limits.get("title_max_length")
        desc_max = limits.get("description_max_length")
        schema = [
            FormField(name="title", label="标题", field_type="text", placeholder="输入视频标题", max_length=title_max),
            FormField(name="description", label="描述", field_type="textarea", placeholder="输入作品描述...", max_length=desc_max),
            FormField(name="tags", label="标签", field_type="text", required=False, placeholder="标签, 用逗号隔开"),
        ]
        return schema

    async def publish(
        self,
        context: Page,
        file_path: str,
        metadata: Dict[str, Any]
    ) -> PublishResult:
        """执行抖音自动发布流程 (基于步骤责任链)

        Args:
            context: Playwright Page 对象（已注入账号凭证）
            file_path: 本地视频文件路径
            metadata: 元数据字典，包含 title, description, tags 等

        Returns:
            PublishResult 发布结果
        """
        page = context
        try:
            logger.info(f"===== 抖音发布插件启动 =====")
            logger.info(f"目标文件: {file_path}")
            USER_LOG.info("发布流程 - 开始")

            # 步骤实现按文件类型（video/image）分支，但整体链路形态保持一致
            from .steps.step_01_home import NavigateHomeStep
            from .steps.step_02_entry import EnterPublishEntryStep
            from .steps.step_03_upload import UploadMediaStep
            from .steps.step_04_description import MetadataFillStep
            from .steps.step_09_submit import SubmitStep
            from .steps.step_05_cover_video import CoverVideoStep
            from .steps.step_05_cover_image import CoverImageStep
            from .steps.step_06_work_declaration import WorkDeclarationStep
            from .steps.step_07b_extra_info import ExtraInfoCommonStep
            from .steps.step_07a_music import SelectMusicStep
            from .steps.step_07c_trending import TrendingStep
            from .steps.step_08_settings import PublishSettingsStep
            from .steps.step_runner import StepRunner, RunnerConfig

            file_type = (metadata.get("file_type") or "video").lower()

            # 统一业务流程（视频/图文均为 9 步）：
            # 步骤1 首页导航
            # 步骤2 进入发布页
            # 步骤3 上传文件
            # 步骤4 填写描述（标题/正文/话题）
            # 步骤5 封面设置（视频：CoverVideoStep；图文：CoverImageStep）
            # 步骤6 作品申明（WorkDeclarationStep）
            # 步骤7 扩展信息（视频：7b标签+7c热点；图文：7a音乐+7b标签+7c热点，子步骤内各自跳过无关字段）
            # 步骤8 发布设置（定时/可见性/保存权限）
            # 步骤9 点击发布
            #
            # 视频流程先填描述，利用这段时间让封面区渲染完毕，步骤5进入时直接点击无需等待
            steps = [
                NavigateHomeStep(),       # 步骤1
                EnterPublishEntryStep(),  # 步骤2
                UploadMediaStep(),        # 步骤3
            ]

            if file_type == "video":
                steps.append(MetadataFillStep())    # 步骤4
                steps.append(CoverVideoStep())      # 步骤5
                steps.append(WorkDeclarationStep())  # 步骤6
                # 步骤7：视频扩展信息（6b标签 + 6c热点）
                steps.append(ExtraInfoCommonStep())
                steps.append(TrendingStep())
            else:
                steps.append(MetadataFillStep())    # 步骤4
                steps.append(CoverImageStep())      # 步骤5
                steps.append(WorkDeclarationStep())  # 步骤6
                # 步骤7：图文扩展信息（6a音乐 + 6b标签 + 6c热点）
                steps.append(SelectMusicStep())
                steps.append(ExtraInfoCommonStep())
                steps.append(TrendingStep())

            steps.append(PublishSettingsStep())  # 步骤8
            steps.append(SubmitStep())           # 步骤9

            # 关键选择器命中探针（失败时输出命中数，帮助快速定位页面改版）；发布层防风控配置
            # 音乐入口仅图文发布页存在，视频任务不注入 music_* 探针，避免误判为「在执行选音乐」
            probes: Dict[str, Any] = {
                "file_input_video": ", ".join(Selectors.PUBLISH.get("FILE_INPUT", [])),
                "file_input_image": ", ".join(Selectors.PUBLISH.get("IMAGE_FILE_INPUT", [])),
                "submit_btn": ", ".join(Selectors.PUBLISH.get("SUBMIT_BTN", [])),
                "cover_btn": ", ".join(Selectors.PUBLISH.get("COVER_BTN", [])),
                "home_publish_video": ", ".join(Selectors.HOME.get("PUBLISH_VIDEO_BTN", [])),
                "home_publish_image": ", ".join(Selectors.HOME.get("PUBLISH_IMAGE_BTN", [])),
                "home_publish_hd": ", ".join(Selectors.HOME.get("PUBLISH_HD_ENTRY_BTN", [])),
            }
            if file_type != "video":
                probes["image_upload_done"] = ", ".join(Selectors.PUBLISH.get("IMAGE_UPLOAD_SUCCESS_MARKER", []))
            if file_type == "image":
                probes["music_select"] = ", ".join(Selectors.PUBLISH.get("MUSIC_ENTRY_SELECT", []))
                probes["music_modify"] = ", ".join(Selectors.PUBLISH.get("MUSIC_ENTRY_MODIFY", []))
            platform_data = _platform_config()
            anti_risk_config = (
                platform_data.get("publish_pacing")
                if isinstance(platform_data.get("publish_pacing"), dict)
                else platform_data.get("anti_risk")
                if isinstance(platform_data.get("anti_risk"), dict)
                else {}
            )
            metadata_for_runner = {**metadata, "selector_probes": probes, "anti_risk_config": anti_risk_config}
            runner = StepRunner(
                page=page,
                file_path=file_path,
                metadata=metadata_for_runner,
                config=RunnerConfig(),
                action_handlers={
                    # Submit 后若提示需要封面/补充信息，通过 Runner 触发相应补救步骤并重试提交
                    "need_cover": (
                        (lambda: [CoverVideoStep()])
                        if file_type == "video"
                        else (lambda: [CoverImageStep()])
                    ),
                    "need_supplement": (
                        (lambda: [ExtraInfoCommonStep()])
                        if file_type == "video"
                        else (lambda: [SelectMusicStep(), ExtraInfoCommonStep()])
                    ),
                },
            )
            result = await runner.run(steps)
            if result.success:
                USER_LOG.info("发布流程 - 完成")
                # 适当延迟几秒关闭浏览器，避免关闭过快
                await asyncio.sleep(5.0)
            else:
                USER_LOG.warning(f"发布流程 - 失败: {(result.error_message or '')[:50]}")
            return result

        except Exception as e:
            logger.error(f"抖音发布插件异常: {e}", exc_info=True)
            USER_LOG.warning(f"发布流程 - 失败: 插件异常")
            return PublishResult(success=False, error_message=f"插件执行异常: {str(e)}")
