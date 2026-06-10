"""Deterministic browser interaction helpers.

The historical API names are retained for plugin compatibility. The helpers no
longer inject purposeless browsing, random pointer movement, random click
coordinates, or deliberate typing mistakes.
"""

from typing import Dict, Any, Optional, Union

from src.infrastructure.browser.automation_api import Page, Locator


async def random_mouse_wander(
    page: Page,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    """Compatibility no-op: purposeless pointer movement is disabled."""
    return None


async def optional_browse_before_action(
    page: Page,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    """Compatibility no-op: unrelated pre-action browsing is disabled."""
    return None


async def human_click(
    page: Page,
    selector_or_locator: Union[str, Locator],
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
    *,
    use_operation_delay: bool = True,
) -> None:
    """Scroll the target into view and use Playwright's normal actionability click."""
    locator = (
        page.locator(selector_or_locator)
        if isinstance(selector_or_locator, str)
        else selector_or_locator
    )
    await locator.scroll_into_view_if_needed()
    await locator.click()


async def human_type_text(
    page: Page,
    selector: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
    *,
    use_operation_delay: bool = True,
    clear_first: bool = True,
) -> None:
    """Enter text with normal keyboard events and no deliberate mistakes."""
    locator = page.locator(selector)
    await locator.scroll_into_view_if_needed()
    if clear_first:
        await locator.clear()
    await locator.click()
    rate = max(0.1, float((metadata or {}).get("speed_rate", 1.0)))
    await locator.press_sequentially(text, delay=max(10, int(30 * rate)))
