# 抖音步骤运行器 — 继承通用 GenericStepRunner，仅定义平台差异
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.plugins.core.step_runner import GenericStepRunner, BaseRunnerConfig

STEP_DISPLAY_NAMES = {
    "NavigateHomeStep": "导航首页",
    "EnterPublishEntryStep": "进入发布页",
    "UploadMediaStep": "上传视频/图文",
    "MetadataFillStep": "作品描述",
    "CoverVideoStep": "视频封面",
    "CoverImageStep": "图文封面",
    "ExtraInfoCommonStep": "扩展信息",
    "SelectMusicStep": "选择音乐",
    "PublishSettingsStep": "发布设置",
    "SubmitStep": "点击发布",
}

MAIN_PHASES: List[Tuple[str, ...]] = [
    ("NavigateHomeStep",),
    ("EnterPublishEntryStep",),
    ("UploadMediaStep",),
    ("MetadataFillStep",),
    ("CoverVideoStep", "CoverImageStep"),
    ("SelectMusicStep", "ExtraInfoCommonStep"),
    ("PublishSettingsStep",),
    ("SubmitStep",),
]

_SKIP_BROWSE_STEPS = {"CoverVideoStep"}


@dataclass
class RunnerConfig(BaseRunnerConfig):
    screenshot_platform: str = "douyin"


class StepRunner(GenericStepRunner):
    MAIN_PHASES = MAIN_PHASES
    STEP_DISPLAY_NAMES = STEP_DISPLAY_NAMES

    def _should_skip_browse(self, step_name: str) -> bool:
        return step_name in _SKIP_BROWSE_STEPS

    def _get_step_max_retries(self, step_name: str, default_max_retries: int) -> int:
        # 需求：抖音步骤三（上传）失败后不重试，直接返回失败。
        if step_name == "UploadMediaStep":
            return 1
        return default_max_retries
