"""
发布步骤基类（多插件共用）
文件路径：src/plugins/core/steps_base.py
功能：抖音、视频号等插件的发布步骤协议与基类，供各插件 steps/_base.py re-export
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional, Literal, Union

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult


@dataclass(frozen=True)
class NeedsAction:
    """步骤链中的“可补救动作”信号。

    用于在 Submit 后遇到“需要封面/补充信息”等阻塞时，返回给上层 Runner 处理并重试提交。
    """

    action: Literal["need_cover", "need_supplement", "need_retry"]
    message: str = ""


StepOutcome = Optional[Union[PublishResult, NeedsAction]]


class BasePublishStep(ABC):
    @abstractmethod
    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        """
        执行当前发布步骤

        Args:
            page: Playwright Page 对象
            file_path: 视频/图片文件路径
            metadata: 元数据信息 (标题、描述等)

        Returns:
            None 表示成功执行完毕当前步骤，流程可放行继续
            PublishResult 表示该步骤发生中断、错误或流程完结，需抛出给外层
            NeedsAction 表示需要补齐信息或做特定动作后再继续/重试
        """
        pass

    async def _await_pause(self, metadata: Dict[str, Any]) -> None:
        """检查并等待暂停事件"""
        pause_event = metadata.get("pause_event")
        if pause_event is not None and hasattr(pause_event, "wait"):
            await pause_event.wait()

    def _step_prefix(self, metadata: Dict[str, Any], display_name: str) -> str:
        """返回动态步骤前缀，如 [步骤6/12 添加音乐]。
        优先使用 runner 注入的 _step_prefix；若不存在则用 _step_idx/_total_steps 拼装；最终兜底用 display_name。
        """
        injected = metadata.get("_step_prefix")
        if injected:
            # runner 注入的 prefix 已含显示名，直接替换其中的显示名部分以使用调用方指定的名称
            # 格式：[步骤X/N 原显示名] → [步骤X/N display_name]
            import re as _re
            replaced = _re.sub(r'(\[步骤\d+/\d+)\s+[^\]]+\]', rf'\1 {display_name}]', injected)
            if replaced != injected:
                return replaced
            return injected
        idx = metadata.get("_step_idx")
        total = metadata.get("_total_steps")
        if idx is not None and total is not None:
            return f"[步骤{idx}/{total} {display_name}]"
        return f"[{display_name}]"
