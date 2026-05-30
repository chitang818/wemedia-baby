# 小红书步骤运行器 — 继承通用 GenericStepRunner
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

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

# 同一张发布编辑页内连续子步骤：跳过 0.5~3s 步骤间等待，改为约 80ms 停顿
_SKIP_STEP_INTERVAL_EDGES: Set[Tuple[str, str]] = {
    ("CoverSettingStep", "MetadataFillStep"),
    ("MetadataFillStep", "OriginalDeclarationStep"),
    ("OriginalDeclarationStep", "WorkDeclarationStep"),
    ("WorkDeclarationStep", "LocationStep"),
    ("LocationStep", "PublishSettingsStep"),
}

# 发布编辑页内步骤无需步骤前随机浏览
_SKIP_BROWSE_STEPS: Set[str] = {
    "CoverSettingStep",
    "MetadataFillStep",
    "OriginalDeclarationStep",
    "WorkDeclarationStep",
    "LocationStep",
    "PublishSettingsStep",
    "SubmitStep",
}


@dataclass
class RunnerConfig(BaseRunnerConfig):
    screenshot_platform: str = "xiaohongshu"


class StepRunner(GenericStepRunner):
    MAIN_PHASES = MAIN_PHASES
    STEP_DISPLAY_NAMES = STEP_DISPLAY_NAMES

    def _should_skip_browse(self, step_name: str) -> bool:
        return step_name in _SKIP_BROWSE_STEPS

    def _should_skip_step_interval(
        self, completed_step: str, next_step: Optional[str],
    ) -> bool:
        if not next_step:
            return False
        if (completed_step, next_step) in _SKIP_STEP_INTERVAL_EDGES:
            import random
            import logging
            
            # 行为随机性增强：即使是表单内连续步骤，也有 15% 概率放弃加速，进行普通的长间隔停顿
            if random.random() < 0.15:
                logging.getLogger(__name__).info("随机行为触发：放弃连续快速操作，执行正常步骤间隔等待")
                return False
            return True
        return False
