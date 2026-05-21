# 视频号步骤运行器 — 继承通用 GenericStepRunner，仅定义平台差异
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.plugins.core.step_runner import GenericStepRunner, BaseRunnerConfig

STEP_DISPLAY_NAMES = {
    "NavigateHomeStep": "进入创作者服务中心",
    "EnterPublishEntryStep": "查找发布入口并进入",
    "UploadMediaStep": "上传视频/图片",
    "CoverSettingStep": "封面设置",
    "ImageTitleStep": "填写图文标题",
    "MetadataFillStep": "填写描述",
    "ImageTextMusicStep": "选择并设置背景音乐",
    "LocationSettingStep": "位置设置",
    "LinkSettingStep": "链接设置",
    "ScheduleSettingStep": "定时发表设置",
    "ShortTitleStep": "短标题",
    "OriginalDeclareStep": "声明原创",
    "SubmitStep": "点击发布",
}

MAIN_PHASES: List[Tuple[str, ...]] = [
    ("NavigateHomeStep",),
    ("EnterPublishEntryStep",),
    ("UploadMediaStep",),
    ("CoverSettingStep",),
    ("ImageTitleStep",),
    ("MetadataFillStep",),
    ("LocationSettingStep",),
    ("LinkSettingStep",),
    ("ScheduleSettingStep",),
    ("ShortTitleStep",),
    ("OriginalDeclareStep",),
    ("SubmitStep",),
]

VIDEO_MAIN_PHASES: List[Tuple[str, ...]] = [
    ("NavigateHomeStep",),
    ("EnterPublishEntryStep",),
    ("UploadMediaStep",),
    ("CoverSettingStep",),
    ("MetadataFillStep",),
    ("LocationSettingStep",),
    ("LinkSettingStep",),
    # 步骤8：高级设置（定时 + 短标题 + 原创声明）
    ("ScheduleSettingStep", "ShortTitleStep", "OriginalDeclareStep"),
    ("SubmitStep",),
]

IMAGE_MAIN_PHASES: List[Tuple[str, ...]] = [
    ("NavigateHomeStep",),
    ("EnterPublishEntryStep",),
    ("UploadMediaStep",),
    ("CoverSettingStep",),
    # 步骤5：填写标题与描述（图文专属标题 + 通用描述）
    ("ImageTitleStep", "MetadataFillStep"),
    ("LocationSettingStep",),
    ("LinkSettingStep",),
    # 步骤8：高级设置（背景音乐 + 定时发表）
    ("ImageTextMusicStep", "ScheduleSettingStep"),
    ("SubmitStep",),
]


@dataclass
class RunnerConfig(BaseRunnerConfig):
    screenshot_platform: str = "wechat_video"


class StepRunner(GenericStepRunner):
    MAIN_PHASES = MAIN_PHASES
    STEP_DISPLAY_NAMES = STEP_DISPLAY_NAMES

    def __init__(self, page, file_path, metadata, config=None, action_handlers=None):
        file_type = (metadata.get("file_type") or "video").lower() if metadata else "video"
        self.MAIN_PHASES = IMAGE_MAIN_PHASES if file_type == "image" else VIDEO_MAIN_PHASES
        super().__init__(page, file_path, metadata, config=config, action_handlers=action_handlers)
