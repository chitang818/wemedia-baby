from __future__ import annotations

from typing import cast

import pytest

from src.infrastructure.browser.automation_api import Page
from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.step_runner import BaseRunnerConfig, GenericStepRunner
from src.plugins.core.steps_base import BasePublishStep


class _RiskStep(BasePublishStep):
    calls = 0

    async def execute(self, page, file_path, metadata):
        self.calls += 1
        return PublishResult(success=False, error_message="平台提示操作频繁，请稍后重试")


@pytest.mark.asyncio
async def test_risk_result_is_not_retried(monkeypatch) -> None:
    step = _RiskStep()
    runner = GenericStepRunner(
        page=cast(Page, object()),
        file_path="video.mp4",
        metadata={},
        config=BaseRunnerConfig(max_step_retries=3, diagnostics_on_error=False),
    )

    result = await runner.run([step])

    assert result.success is False
    assert step.calls == 1
    assert "操作频繁" in (result.error_message or "")


@pytest.mark.asyncio
async def test_need_retry_action_is_not_retried() -> None:
    from src.plugins.core.steps_base import NeedsAction

    runner = GenericStepRunner(page=cast(Page, object()), file_path="", metadata={})

    assert await runner._handle_action(NeedsAction(action="need_retry", message="操作频繁")) is False
