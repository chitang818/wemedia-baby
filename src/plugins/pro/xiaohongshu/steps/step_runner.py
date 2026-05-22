# 小红书步骤运行器 — 继承通用 GenericStepRunner
from dataclasses import dataclass
from typing import List, Tuple

from src.plugins.core.step_runner import GenericStepRunner, BaseRunnerConfig

STEP_DISPLAY_NAMES = {
    "NavigateHomeStep": "进入创作者服务平台",
    "EnterPublishEntryStep": "进入发布页",
    "UploadMediaStep": "上传素材",
    "MetadataFillStep": "作品描述",
    "CoverSettingStep": "封面设置",
    "OriginalDeclarationStep": "原创申明",
    "WorkDeclarationStep": "作品申明",
    "LocationStep": "添加地点",
    "PublishSettingsStep": "发布设置",
    "SubmitStep": "点击发布",
}

MAIN_PHASES: List[Tuple[str, ...]] = [
    ("NavigateHomeStep",),
    ("EnterPublishEntryStep",),
    ("UploadMediaStep",),
    ("CoverSettingStep",),
    ("MetadataFillStep",),
    ("OriginalDeclarationStep", "WorkDeclarationStep", "LocationStep"),
    ("PublishSettingsStep",),
    ("SubmitStep",),
]


@dataclass
class RunnerConfig(BaseRunnerConfig):
    screenshot_platform: str = "xiaohongshu"


class StepRunner(GenericStepRunner):
    MAIN_PHASES = MAIN_PHASES
    STEP_DISPLAY_NAMES = STEP_DISPLAY_NAMES
