# -*- coding: utf-8 -*-
"""
视频号发布插件（步骤链版本）
文件路径：src/plugins/pro/wechat_video/publish_plugin.py

采用与抖音插件一致的「步骤链 + StepRunner」架构。对外统一为 **9 个阶段**（日志 `[步骤X/9]`），
视频与图文在「上传之后」分叉：

**共用前缀（阶段 1～4）**：首页 → 发布入口 → 上传 → 封面

**阶段 5～9（随类型变化）**：
- 视频：描述 → 位置 → 链接 →（定时 + 短标题 + 原创）→ 发表
- 图文：图文标题 + 描述 → 位置 → 链接 →（音乐占位 + 定时）→ 发表
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from playwright.async_api import Page

from src.infrastructure.common.bundled_config import load_platform_bundle
from src.plugins.core.interfaces.publish_plugin import (
    PublishPluginInterface,
    PublishResult,
    FormField,
)

logger = logging.getLogger(__name__)


def _wechat_video_bundle() -> Dict[str, Any]:
    """内置 config/platforms/wechat_video.json（含 limits、anti_risk）。"""
    return load_platform_bundle("wechat_video")


def _load_limits() -> Dict[str, int]:
    """加载平台字数限制。优先读取内置 wechat_video.json，兜底插件目录 config.json。"""
    defaults = {
        "title_max_length": 30,
        "description_max_length": 1000,
        "max_topics": 3,
    }
    data = _wechat_video_bundle()
    limits = data.get("limits", {})
    if isinstance(limits, dict) and limits:
        defaults.update(limits)
        return defaults
    try:
        local_cfg = Path(__file__).resolve().parent / "config.json"
        if local_cfg.exists():
            raw = json.loads(local_cfg.read_text(encoding="utf-8"))
            defaults.update(raw.get("limits", {}))
    except Exception:
        pass
    return defaults


def _load_platform_config() -> Dict[str, Any]:
    """从内置 wechat_video.json 读取 anti_risk。"""
    data = _wechat_video_bundle()
    ar = data.get("anti_risk")
    return ar if isinstance(ar, dict) else {}


class WechatVideoPublishPlugin(PublishPluginInterface):
    """视频号发布插件 — 步骤链模式（统一 9 阶段）"""

    @property
    def platform_id(self) -> str:
        return "wechat_video"

    def get_form_schema(self, content_type: str = "video") -> List[FormField]:
        """返回视频号发布表单字段定义（供 UI 动态渲染）"""
        limits = _load_limits()
        schema = [
            FormField(
                name="title",
                label="标题",
                field_type="text",
                required=False,
                max_length=limits.get("title_max_length", 30),
                placeholder="填写作品标题",
            ),
            FormField(
                name="description",
                label="描述",
                field_type="textarea",
                required=False,
                max_length=limits.get("description_max_length", 1000),
                placeholder="填写作品描述...",
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
        """执行视频号发布流程（对外 9 个阶段，详见模块顶部说明）。"""
        page = context

        # 加载防风控配置
        anti_risk_config = _load_platform_config()
        metadata["anti_risk_config"] = anti_risk_config

        file_type = (metadata.get("file_type") or "video").lower()

        # 组装步骤链。视频与图文在上传后分叉：图文先填标题，再填描述；图文不走短标题步骤。
        from .steps.step_01_home import NavigateHomeStep
        from .steps.step_02_entry import EnterPublishEntryStep
        from .steps.step_03_upload import UploadMediaStep
        from .steps.step_04_cover import CoverSettingStep
        from .steps.step_05A_image_title import ImageTitleStep
        from .steps.step_05B_description import MetadataFillStep
        from .steps.step_08A_image_music import ImageTextMusicStep
        from .steps.step_06_location import LocationSettingStep
        from .steps.step_07_link import LinkSettingStep
        from .steps.step_08B_schedule import ScheduleSettingStep
        from .steps.step_08C_short_title import ShortTitleStep
        from .steps.step_08D_original import OriginalDeclareStep
        from .steps.step_09_submit import SubmitStep
        from .steps.step_runner import StepRunner, RunnerConfig

        common_prefix_steps = [
            NavigateHomeStep(),       # 步骤1:  进入创作者服务中心
            EnterPublishEntryStep(),  # 步骤2:  查找发布入口并进入
            UploadMediaStep(),        # 步骤3:  上传视频/图片
            CoverSettingStep(),       # 步骤4:  封面设置
        ]

        common_suffix_steps = [
            LocationSettingStep(),    # 阶段6: 位置设置
            LinkSettingStep(),        # 阶段7: 链接设置
            ScheduleSettingStep(),    # 阶段8（视频链内子步骤之一）: 定时发表
            SubmitStep(),             # 阶段9: 点击发布
        ]

        if file_type == "image":
            steps = [
                *common_prefix_steps,
                ImageTitleStep(),      # 步骤5A: 图文标题
                MetadataFillStep(),    # 步骤5B: 填写描述
                LocationSettingStep(), # 步骤6:  位置设置
                LinkSettingStep(),     # 步骤7:  链接设置
                ImageTextMusicStep(),  # 步骤8A: 选择并设置背景音乐（占位）
                ScheduleSettingStep(), # 步骤8B: 定时发表设置
                SubmitStep(),          # 步骤9:  点击发布
            ]
        else:
            steps = [
                *common_prefix_steps,
                MetadataFillStep(),    # 步骤5:  填写描述
                *common_suffix_steps[:3],
                ShortTitleStep(),      # 阶段8：短标题（视频）
                OriginalDeclareStep(), # 阶段8：声明原创（视频）
                *common_suffix_steps[3:],
            ]

        # 补救动作映射（视频号暂无封面补救，仅保留补充信息补救框架）
        action_handlers = {
            "need_supplement": lambda: [SubmitStep()],
        }

        runner = StepRunner(
            page=page,
            file_path=file_path,
            metadata=metadata,
            config=RunnerConfig(
                max_step_retries=3,
                step_retry_delay_seconds=1.5,
                max_submit_retries=2,
            ),
            action_handlers=action_handlers,
        )

        return await runner.run(steps)
