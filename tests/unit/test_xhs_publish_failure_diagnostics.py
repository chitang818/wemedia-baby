# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.plugins.pro.xiaohongshu.publish_failure_diagnostics import (
    build_xhs_failure_analysis,
    format_analysis_txt,
    load_analysis_hints_from_bundle,
)

pytestmark = pytest.mark.unit


def test_build_analysis_submit_disabled_mentions_schedule_overlay() -> None:
    analysis = build_xhs_failure_analysis(
        step_name="SubmitStep",
        reason="等待发布钮可点击超时",
        summary={
            "host_count": 1,
            "submit_disabled": True,
            "submit_text": "定时发布",
            "schedule_picker_open": True,
            "has_sr": True,
        },
        probe={
            "srAccessMethod": "_sr",
            "hostFound": True,
            "submitDisabled": "true",
            "ready": False,
            "reason": "disabled",
        },
    )

    hints_text = "\n".join(analysis["hints"])
    assert "submit-disabled=true" in hints_text
    assert "定时" in hints_text
    assert any("浮层" in h for h in analysis["hints"])
    assert analysis["platform"] == "xiaohongshu"


def test_build_analysis_host_zero_does_not_blame_missing_button_on_pierce() -> None:
    analysis = build_xhs_failure_analysis(
        step_name="UploadStep",
        reason="selector failed",
        summary={"host_count": 0, "submit_disabled": False},
        probe={"srAccessMethod": "none", "hostFound": False},
    )

    hints_text = "\n".join(analysis["hints"])
    assert "未检测到 xhs-publish-btn" in hints_text
    assert "pierce" not in hints_text or "0 属正常" not in hints_text


def test_build_analysis_with_sr_adds_pierce_clarification() -> None:
    analysis = build_xhs_failure_analysis(
        step_name="SubmitStep",
        reason="click failed",
        summary={"host_count": 1, "hostCount": 1, "submit_disabled": False, "has_sr": True},
        probe={"srAccessMethod": "_sr", "hostFound": True},
    )

    assert any("pierce" in h and "属正常" in h for h in analysis["hints"])


def test_format_analysis_txt_includes_sections() -> None:
    analysis = build_xhs_failure_analysis(
        step_name="SubmitStep",
        reason="超时",
        summary={"host_count": 1},
        probe={"srAccessMethod": "_sr"},
    )
    text = format_analysis_txt(analysis)

    assert "【提示】" in text
    assert "xhs_publish_snapshot.json" in text


def test_load_analysis_hints_from_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "case1"
    bundle.mkdir()
    (bundle / "platform_analysis.json").write_text(
        json.dumps({"hints": ["提示一", "提示二", ""]}, ensure_ascii=False),
        encoding="utf-8",
    )

    hints = load_analysis_hints_from_bundle(str(bundle), max_hints=3)

    assert hints == ["提示一", "提示二"]


def test_load_analysis_hints_missing_dir_returns_empty() -> None:
    assert load_analysis_hints_from_bundle("") == []
    assert load_analysis_hints_from_bundle("/nonexistent/path/xyz") == []
