"""CLI for building standalone browser diagnostic comparison reports."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from browser_diagnostic_tool.desktop.project_probe import browser_diagnostics_dir
from browser_diagnostic_tool.shared.report_builder import write_report_bundle


def _load_json(path: str | Path, fallback: Any) -> Any:
    p = Path(path)
    if not p.exists():
        return fallback
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    return data


def _load_snapshots(paths: list[str]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for path in paths:
        data = _load_json(path, {})
        if isinstance(data, list):
            snapshots.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict):
            snapshots.append(data)
    return snapshots


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build browser diagnostic comparison report.")
    parser.add_argument("--platform", required=True, choices=["xiaohongshu", "douyin", "wechat_video"])
    parser.add_argument("--test-run-id", default="")
    parser.add_argument("--snapshot", action="append", default=[], help="Path to a snapshot JSON file. Repeatable.")
    parser.add_argument("--launch-context", default="", help="Optional launch_context.json path.")
    parser.add_argument("--behavior-trace", default="", help="Optional behavior_trace.json path.")
    parser.add_argument("--output-dir", default="", help="Optional output directory.")
    args = parser.parse_args(argv)

    test_run_id = args.test_run_id or datetime.now().strftime("%H%M%S_manual")
    date_part = datetime.now().strftime("%Y%m%d")
    output_dir = Path(args.output_dir) if args.output_dir else browser_diagnostics_dir(args.platform, date_part, test_run_id)
    snapshots = _load_snapshots(args.snapshot)
    launch_context = _load_json(args.launch_context, {}) if args.launch_context else {}
    behavior_trace = _load_json(args.behavior_trace, []) if args.behavior_trace else []
    if not isinstance(behavior_trace, list):
        behavior_trace = []
    if not isinstance(launch_context, dict):
        launch_context = {}

    write_report_bundle(
        output_dir,
        platform=args.platform,
        test_run_id=test_run_id,
        snapshots=snapshots,
        launch_context=launch_context,
        behavior_trace=behavior_trace,
    )
    print(str(output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
