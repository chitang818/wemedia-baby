# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from src.plugins.pro.xiaohongshu.steps.step_runner import StepRunner

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("completed", "next_step", "expected"),
    [
        ("OriginalDeclarationStep", "WorkDeclarationStep", True),
        ("WorkDeclarationStep", "LocationStep", True),
        ("LocationStep", "PublishSettingsStep", True),
        ("NavigateHomeStep", "EnterPublishEntryStep", False),
        ("PublishSettingsStep", "SubmitStep", False),
    ],
)
def test_should_skip_step_interval_edges(
    completed: str, next_step: str, expected: bool,
) -> None:
    runner = StepRunner.__new__(StepRunner)
    assert runner._should_skip_step_interval(completed, next_step) is expected


def test_should_skip_browse_on_publish_form_steps() -> None:
    runner = StepRunner.__new__(StepRunner)
    assert runner._should_skip_browse("WorkDeclarationStep")
    assert not runner._should_skip_browse("UploadMediaStep")
