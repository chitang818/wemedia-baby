from __future__ import annotations

import json

from browser_diagnostic_tool.shared.report_builder import build_comparison_report, write_report_bundle


def _snapshot(mode: str, webdriver: bool, user_data_dir: str = "") -> dict:
    return {
        "collector": "chrome_extension",
        "extension_present": True,
        "controlled_by_playwright": mode != "local_manual",
        "platform": "xiaohongshu",
        "mode": mode,
        "stage": "pre_submit",
        "user_data_dir": user_data_dir,
        "page_environment": {
            "navigator": {
                "webdriver": webdriver,
                "userAgent": "Chrome Test",
                "languages": ["zh-CN", "zh"],
                "userAgentData": {"platform": "Windows"},
            },
            "locale": {"timezone": "Asia/Shanghai"},
            "viewport": {"innerWidth": 1000, "innerHeight": 700},
            "webgl": {"unmaskedRenderer": "ANGLE Test"},
            "permissions": {"notifications": "prompt"},
        },
        "cookies": [{"name": "sid", "value": "secret", "domain": ".xiaohongshu.com"}],
    }


def test_build_comparison_report_marks_differences_and_risks() -> None:
    report = build_comparison_report(
        platform="xiaohongshu",
        test_run_id="case1",
        snapshots=[
            _snapshot("local_manual", False),
            _snapshot("wmb_manual", True, "C:/Users/demo/AppData/Local/WeMediaBaby/data/xhs/user_data"),
        ],
    )

    fields = {row["field"]: row for row in report["comparison"]}
    assert fields["webdriver"]["different"] is True
    assert fields["controlled_by_playwright"]["different"] is True
    assert report["snapshots"][1]["risks"][0]["code"] == "navigator_webdriver_true"
    assert "secret" not in json.dumps(report, ensure_ascii=False)
    assert "sid" in json.dumps(report, ensure_ascii=False)


def test_write_report_bundle_outputs_standard_files(tmp_path) -> None:
    report = write_report_bundle(
        tmp_path,
        platform="xiaohongshu",
        test_run_id="case2",
        snapshots=[_snapshot("local_manual", False)],
        launch_context={"token": "secret", "browser_manager_class": "UndetectedBrowserManager"},
        behavior_trace=[{"stage": "pre_submit", "authorization": "secret"}],
    )

    expected = {
        "snapshots.json",
        "launch_context.json",
        "behavior_trace.json",
        "comparison_report.json",
        "comparison_report.html",
    }
    assert expected.issubset({p.name for p in tmp_path.iterdir()})
    assert report["launch_context"]["token"] == "***REDACTED***"
    assert report["behavior_trace"][0]["authorization"] == "***REDACTED***"
