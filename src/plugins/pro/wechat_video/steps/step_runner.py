# 视频号步骤运行器 — 继承通用 GenericStepRunner，仅定义平台差异
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.plugins.core.step_runner import GenericStepRunner, BaseRunnerConfig

STEP_DISPLAY_NAMES = {
    "NavigateHomeStep": "进入创作者服务中心",
    "EnterPublishEntryStep": "查找发布入口并进入",
    "UploadMediaStep": "上传视频/图片",
    "CoverSettingStep": "封面设置",
    "MetadataFillStep": "填写描述",
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
    ("MetadataFillStep",),
    ("LocationSettingStep",),
    ("LinkSettingStep",),
    ("ScheduleSettingStep",),
    ("ShortTitleStep",),
    ("OriginalDeclareStep",),
    ("SubmitStep",),
]


@dataclass
class RunnerConfig(BaseRunnerConfig):
    screenshot_platform: str = "wechat_video"


class StepRunner(GenericStepRunner):
    MAIN_PHASES = MAIN_PHASES
    STEP_DISPLAY_NAMES = STEP_DISPLAY_NAMES
