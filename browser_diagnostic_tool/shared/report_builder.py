"""Build comparison reports for browser diagnostic snapshots."""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .risk_rules import evaluate_snapshot_risks
from .sanitize import redact_sensitive


COMPARE_FIELDS = (
    ("webdriver", ("page_environment", "navigator", "webdriver")),
    ("user_agent", ("page_environment", "navigator", "userAgent")),
    ("ua_ch_platform", ("page_environment", "navigator", "userAgentData", "platform")),
    ("languages", ("page_environment", "navigator", "languages")),
    ("timezone", ("page_environment", "locale", "timezone")),
    ("viewport", ("page_environment", "viewport")),
    ("webgl_renderer", ("page_environment", "webgl", "unmaskedRenderer")),
    ("permissions", ("page_environment", "permissions")),
    ("controlled_by_playwright", ("controlled_by_playwright",)),
    ("user_data_dir", ("user_data_dir",)),
    ("extension_present", ("extension_present",)),
)


def _deep_get(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = data
    for part in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    clean = redact_sensitive(snapshot)
    if not isinstance(clean, dict):
        return {}
    clean.setdefault("risks", evaluate_snapshot_risks(clean))
    return clean


def build_comparison_report(
    *,
    platform: str,
    test_run_id: str,
    snapshots: list[dict[str, Any]],
    launch_context: dict[str, Any] | None = None,
    behavior_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a sanitized JSON report from one or more snapshots."""

    clean_snapshots = [_normalize_snapshot(item) for item in snapshots if isinstance(item, dict)]
    rows: list[dict[str, Any]] = []
    for name, path in COMPARE_FIELDS:
        values: dict[str, Any] = {}
        for snapshot in clean_snapshots:
            label = f"{snapshot.get('mode', 'unknown')}:{snapshot.get('stage', 'unknown')}"
            values[label] = _deep_get(snapshot, path)
        unique_json = {json.dumps(v, sort_keys=True, ensure_ascii=False, default=str) for v in values.values()}
        rows.append({"field": name, "values": values, "different": len(unique_json) > 1})

    return {
        "schema_version": "1.0",
        "platform": platform,
        "test_run_id": test_run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "snapshots": clean_snapshots,
        "launch_context": redact_sensitive(launch_context or {}),
        "behavior_trace": redact_sensitive(behavior_trace or []),
        "comparison": rows,
    }


def _format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = "" if value is None else str(value)
    return html.escape(text)


def render_report_html(report: dict[str, Any]) -> str:
    rows = []
    for row in report.get("comparison", []):
        values = row.get("values") if isinstance(row, dict) else {}
        value_html = "<br>".join(
            f"<b>{html.escape(str(k))}</b>: {_format_value(v)}"
            for k, v in (values or {}).items()
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('field', '')))}</td>"
            f"<td>{'Yes' if row.get('different') else 'No'}</td>"
            f"<td>{value_html}</td>"
            "</tr>"
        )

    risks = []
    for snapshot in report.get("snapshots", []):
        label = f"{snapshot.get('mode', 'unknown')}:{snapshot.get('stage', 'unknown')}"
        for risk in snapshot.get("risks", []):
            risks.append(
                "<li>"
                f"<b>{html.escape(label)}</b> "
                f"[{html.escape(str(risk.get('level', '')))}] "
                f"{html.escape(str(risk.get('message', '')))}"
                "</li>"
            )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Browser Diagnostic Report</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 24px; color: #1f2937; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; vertical-align: top; }}
    th {{ background: #f3f4f6; text-align: left; }}
    code {{ background: #f3f4f6; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Browser Diagnostic Report</h1>
  <p>Platform: <code>{html.escape(str(report.get('platform', '')))}</code></p>
  <p>Test run: <code>{html.escape(str(report.get('test_run_id', '')))}</code></p>
  <h2>Risk Hints</h2>
  <ul>{''.join(risks) or '<li>No rule-based risk hints.</li>'}</ul>
  <h2>Comparison</h2>
  <table>
    <thead><tr><th>Field</th><th>Different</th><th>Values</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""


def write_report_bundle(
    output_dir: str | Path,
    *,
    platform: str,
    test_run_id: str,
    snapshots: list[dict[str, Any]],
    launch_context: dict[str, Any] | None = None,
    behavior_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Write the standard diagnostic report files and return the report dict."""

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = build_comparison_report(
        platform=platform,
        test_run_id=test_run_id,
        snapshots=snapshots,
        launch_context=launch_context,
        behavior_trace=behavior_trace,
    )
    (out / "snapshots.json").write_text(
        json.dumps(report["snapshots"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "launch_context.json").write_text(
        json.dumps(report["launch_context"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "behavior_trace.json").write_text(
        json.dumps(report["behavior_trace"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "comparison_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "comparison_report.html").write_text(render_report_html(report), encoding="utf-8")
    return report

