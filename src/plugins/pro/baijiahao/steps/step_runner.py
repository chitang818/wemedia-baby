# 百家号步骤运行器 — 继承通用 GenericStepRunner
from dataclasses import dataclass
from typing import List, Tuple

from src.plugins.core.step_runner import GenericStepRunner, BaseRunnerConfig

STEP_DISPLAY_NAMES = {
    "NavigateHomeStep": "进入创作中心",
    "EnterPublishEntryStep": "进入发布页",
    "UploadMediaStep": "上传素材",
    "MetadataFillStep": "作品描述",
    "CoverSettingStep": "封面设置",
    "PublishSettingsStep": "发布设置",
    "SubmitStep": "点击发布",
}

MAIN_PHASES: List[Tuple[str, ...]] = [
    ("NavigateHomeStep",),
    ("EnterPublishEntryStep",),
    ("UploadMediaStep",),
    ("MetadataFillStep",),
    ("CoverSettingStep",),
    ("PublishSettingsStep",),
    ("SubmitStep",),
]


@dataclass
class RunnerConfig(BaseRunnerConfig):
    screenshot_platform: str = "baijiahao"


class StepRunner(GenericStepRunner):
    MAIN_PHASES = MAIN_PHASES
    STEP_DISPLAY_NAMES = STEP_DISPLAY_NAMES
