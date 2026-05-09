# 快手步骤运行器 — 继承通用 GenericStepRunner，仅定义平台差异
#
# 步骤链在 publish_plugin.py 按发布类型动态组装：
#   视频与图文对外统一为 11 个阶段（[步骤X/11]）：
#   视频：步骤1~5 → 6 仅 6b(作者服务) → 7~11
#   图文：步骤1~5 → 6 含 6a(音乐)+6b(作者服务) 两个小步骤，进度同属第 6 阶段 → 7~11
# run() 时将连续的 MusicSettingStep+AuthorServiceStep 合并为一个 phase，保证总数恒为 11。
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from src.plugins.core.step_runner import GenericStepRunner, BaseRunnerConfig, _build_phase_index
from src.plugins.core.steps_base import BasePublishStep


def _build_kuaishou_phase_groups(step_list: List[BasePublishStep]) -> List[Tuple[str, ...]]:
    """将实际步骤列表转为阶段组：图文时 6a+6b 合并为同一阶段编号。"""
    names = [s.__class__.__name__ for s in step_list]
    out: List[Tuple[str, ...]] = []
    i = 0
    n = len(names)
    while i < n:
        if (
            names[i] == "MusicSettingStep"
            and i + 1 < n
            and names[i + 1] == "AuthorServiceStep"
        ):
            out.append(("MusicSettingStep", "AuthorServiceStep"))
            i += 2
        else:
            out.append((names[i],))
            i += 1
    return out

STEP_DISPLAY_NAMES = {
    "NavigateHomeStep":    "导航首页",
    "EnterPublishEntryStep": "进入发布页",
    "UploadMediaStep":     "上传媒体",
    "MetadataFillStep":    "作品描述",
    "CoverSettingStep":    "封面设置",
    "MusicSettingStep":    "添加音乐",   # 仅图文
    "AuthorServiceStep":   "作者服务",
    "ManageHotspotStep":   "关联热点",
    "AuthorStatementStep": "作者声明",
    "LocationStep":        "添加地点",
    "PublishSettingsStep": "发布设置",
    "SubmitStep":          "点击发布",
}

# 统一 11 阶段模板；第 6 阶段在图文时对应 6a+6b 两个可执行步骤，在视频时仅含 6b
MAIN_PHASES: List[Tuple[str, ...]] = [
    ("NavigateHomeStep",),
    ("EnterPublishEntryStep",),
    ("UploadMediaStep",),
    ("MetadataFillStep",),
    ("CoverSettingStep",),
    ("MusicSettingStep", "AuthorServiceStep"),
    ("ManageHotspotStep",),
    ("AuthorStatementStep",),
    ("LocationStep",),
    ("PublishSettingsStep",),
    ("SubmitStep",),
]


@dataclass
class RunnerConfig(BaseRunnerConfig):
    screenshot_platform: str = "kuaishou"


class StepRunner(GenericStepRunner):
    MAIN_PHASES = MAIN_PHASES
    STEP_DISPLAY_NAMES = STEP_DISPLAY_NAMES

    def run(self, steps: Iterable[BasePublishStep]):
        """运行前重建进度索引：视频/图文均为 11 阶段，图文步骤 6 的 6a+6b 共用阶段号 6。"""
        step_list = list(steps)
        actual_phases = _build_kuaishou_phase_groups(step_list)
        self._phase_index = _build_phase_index(actual_phases)
        self._total_phases = len(actual_phases)
        return super().run(step_list)

    def _get_retry_delay(self, step_name: str, attempt: int, base_delay: float) -> float:
        if step_name == "UploadMediaStep" and attempt > 1:
            return min(base_delay * (2 ** (attempt - 1)), 10.0)
        return base_delay
