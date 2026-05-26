# -*- coding: utf-8 -*-
"""快手步骤 8 作者声明单元测试"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.publish.work_declaration import (
    KEY_KUAISHOU,
    KEY_KUAISHOU_AUTO,
    KUAISHOU_CHOICES,
    KUAISHOU_DECLARATION_OPTIONS,
    KUAISHOU_DECLARATION_PLACEHOLDER,
    KUAISHOU_FICTION,
    KUAISHOU_PERSONAL,
    kuaishou_declaration_click_texts,
    label_for_kuaishou_value,
    normalize_kuaishou_value,
)
from src.plugins.community.kuaishou.steps.step_08_author_statement import (
    AuthorStatementStep,
)
from src.plugins.core.interfaces.publish_plugin import PublishResult


def test_kuaishou_choices_match_dom_labels() -> None:
    labels = [label for _, label in KUAISHOU_CHOICES]
    assert labels == list(KUAISHOU_DECLARATION_OPTIONS)
    assert "演绎情节，仅供娱乐" in labels
    assert "个人观点，仅供参考" in labels
    assert KUAISHOU_DECLARATION_PLACEHOLDER == "为作品添加补充说明"


def test_label_for_kuaishou_personal_canonical() -> None:
    assert label_for_kuaishou_value(KUAISHOU_PERSONAL) == "个人观点，仅供参考"
    assert label_for_kuaishou_value(KUAISHOU_FICTION) == "演绎情节，仅供娱乐"


def test_normalize_kuaishou_legacy_typo_label() -> None:
    assert normalize_kuaishou_value("个人观点经供参考") == KUAISHOU_PERSONAL
    assert normalize_kuaishou_value("演绎情节仅供参考") == KUAISHOU_FICTION


def test_kuaishou_declaration_click_texts_canonical_then_legacy() -> None:
    texts = kuaishou_declaration_click_texts(KUAISHOU_PERSONAL)
    assert texts[0] == "个人观点，仅供参考"
    assert "个人观点经供参考" in texts

    fiction_texts = kuaishou_declaration_click_texts(KUAISHOU_FICTION)
    assert fiction_texts[0] == "演绎情节，仅供娱乐"
    assert "演绎情节仅供参考" in fiction_texts


@pytest.mark.asyncio
async def test_execute_skips_when_auto_disabled() -> None:
    step = AuthorStatementStep()
    page = MagicMock()
    metadata = {
        "privacy_settings": {
            KEY_KUAISHOU: KUAISHOU_PERSONAL,
            KEY_KUAISHOU_AUTO: False,
        },
        "_step_prefix": "[步骤8/11 作者声明]",
    }
    result = await step.execute(page, "", metadata)
    assert result is None


@pytest.mark.asyncio
async def test_execute_skips_when_not_configured() -> None:
    step = AuthorStatementStep()
    page = MagicMock()
    metadata = {
        "privacy_settings": {KEY_KUAISHOU_AUTO: True},
        "_step_prefix": "[步骤8/11 作者声明]",
    }
    result = await step.execute(page, "", metadata)
    assert result is None


@pytest.mark.asyncio
async def test_execute_fails_when_click_fails() -> None:
    step = AuthorStatementStep()
    page = MagicMock()
    metadata = {
        "privacy_settings": {
            KEY_KUAISHOU: KUAISHOU_PERSONAL,
            KEY_KUAISHOU_AUTO: True,
        },
        "_step_prefix": "[步骤8/11 作者声明]",
    }
    with patch.object(
        step,
        "_apply_kuaishou_declaration",
        new=AsyncMock(return_value=(False, "")),
    ):
        result = await step.execute(page, "", metadata)

    assert isinstance(result, PublishResult)
    assert result.success is False
    assert result.failed_step == "AuthorStatementStep"
    assert "未能选中" in (result.error_message or "")


@pytest.mark.asyncio
async def test_execute_succeeds_when_click_ok() -> None:
    step = AuthorStatementStep()
    page = MagicMock()
    metadata = {
        "privacy_settings": {
            KEY_KUAISHOU: KUAISHOU_PERSONAL,
            KEY_KUAISHOU_AUTO: True,
        },
        "_step_prefix": "[步骤8/11 作者声明]",
    }
    with patch.object(
        step,
        "_apply_kuaishou_declaration",
        new=AsyncMock(return_value=(True, "个人观点，仅供参考")),
    ):
        result = await step.execute(page, "", metadata)

    assert result is None
