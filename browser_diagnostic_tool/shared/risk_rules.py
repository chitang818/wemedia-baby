"""Rule-based risk hints for browser environment diagnostics."""

from __future__ import annotations

from typing import Any


def _get(snapshot: dict[str, Any], *path: str) -> Any:
    cur: Any = snapshot
    for part in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def evaluate_snapshot_risks(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    """Evaluate a single sanitized snapshot and return explainable risk hints."""

    risks: list[dict[str, str]] = []
    webdriver = _get(snapshot, "page_environment", "navigator", "webdriver")
    if webdriver is True:
        risks.append(
            {
                "level": "high",
                "code": "navigator_webdriver_true",
                "message": "navigator.webdriver is true; the page can observe automation control.",
            }
        )

    controlled = snapshot.get("controlled_by_playwright")
    if controlled is True:
        risks.append(
            {
                "level": "high",
                "code": "controlled_by_playwright",
                "message": "The browser session is controlled by Playwright/CDP.",
            }
        )

    user_data_dir = str(snapshot.get("user_data_dir") or "").strip()
    if user_data_dir and "wemediababy" in user_data_dir.lower():
        risks.append(
            {
                "level": "medium",
                "code": "wmb_profile_dir",
                "message": "The browser uses a WeMediaBaby-managed profile instead of the user's daily Chrome profile.",
            }
        )

    prompts = snapshot.get("risk_prompt_snippets")
    if isinstance(prompts, list) and prompts:
        risks.append(
            {
                "level": "high",
                "code": "visible_risk_prompt",
                "message": "Visible page text contains risk, verification, automation, or safety prompt keywords.",
            }
        )

    extension_present = snapshot.get("extension_present")
    if extension_present is True:
        risks.append(
            {
                "level": "info",
                "code": "extension_present",
                "message": "The diagnostic extension is present and must be considered part of the observed environment.",
            }
        )

    return risks

