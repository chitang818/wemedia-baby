# -*- coding: utf-8 -*-
from src.ui.pages.publish.task_field_display import (
    TASK_FIELD_EMPTY_DISPLAY,
    task_field_str_or_dash,
)


def test_task_field_empty_and_whitespace():
    assert task_field_str_or_dash(None) == TASK_FIELD_EMPTY_DISPLAY
    assert task_field_str_or_dash("") == TASK_FIELD_EMPTY_DISPLAY
    assert task_field_str_or_dash("   ") == TASK_FIELD_EMPTY_DISPLAY
    assert task_field_str_or_dash(0) == "0"


def test_task_field_nonempty():
    assert task_field_str_or_dash("  ab  ") == "ab"
