"""多多视频发布步骤基类：从 core 统一基类 re-export，供本插件各 step 使用。"""
from src.plugins.core.steps_base import NeedsAction, StepOutcome, BasePublishStep

__all__ = ["NeedsAction", "StepOutcome", "BasePublishStep"]
